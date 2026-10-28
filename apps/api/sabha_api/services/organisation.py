"""Units and people, set up by owners and admins (owner's decisions, 2026-10-28):

- units are two levels, a top-level unit and the ones under it (a school's classes and sections; the words come from
  the tenant's labels unit_group / unit_sub): POST /v1/units {name, parent_id?}, PATCH /v1/units/{id} {name};
- people (the staff analysed, a school's teachers) are records only, no login: POST /v1/people {name, unit_ids},
  PATCH /v1/people/{id} {name?, unit_ids?}. A teacher may work in several units; the first is their home unit.

Owners and admins only. Every change is audited. Names are unique among siblings (case-insensitive), so a list
never shows two "Section A" under one class.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, ConflictError, ForbiddenError, NotFoundError
from sabha_core.models import AuditEntry, Person, Unit
from sabha_core.repo import TenantRepo

ALLOWED = frozenset({Role.OWNER, Role.ADMIN})
UNIT_ROUTE = "POST /v1/units"
PERSON_ROUTE = "POST /v1/people"

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class UnitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    parent_id: str | None = None  # None: a top-level unit (a class); else the unit it sits under (a section)


class UnitRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class UnitOut(BaseModel):
    id: str
    name: str
    parent_id: str | None


class PersonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    unit_ids: list[str] = Field(default_factory=list, max_length=50)


class PersonChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    unit_ids: list[str] | None = Field(default=None, max_length=50)


class PersonOut(BaseModel):
    id: str
    name: str
    unit_id: str | None
    unit_ids: list[str]


class UnitExistsError(ConflictError):
    code, title = "unit_exists", "Name already used"


class UnknownUnitError(ApiError):  # 422 like the other routes' unknown_unit (invites, recordings)
    status, code, title = 422, "unknown_unit", "Unknown unit"


class TooDeepError(ApiError):
    status, code, title = 422, "unit_too_deep", "Too many levels"


def require_admin(principal: Principal) -> None:
    if principal.role not in ALLOWED:
        raise ForbiddenError("Only owners and administrators can change this.")


async def _check_name(units: TenantRepo[Unit], name: str, parent_id: str | None, except_id: str | None = None) -> None:
    query: dict[str, object] = {"parent_id": parent_id, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    found = await units.find(query)
    if any(u.id != except_id for u in found):
        raise UnitExistsError(f"There is already a “{name}” here.")


async def create_unit(
    principal: Principal, body: UnitIn, request: Request, *, units: TenantRepo[Unit], entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> UnitOut:  # fmt: skip
    require_admin(principal)
    if body.parent_id is not None:
        parent = await units.find_one({"_id": body.parent_id})
        if parent is None:
            raise UnknownUnitError("That unit does not exist in your organisation.")
        if parent.parent_id is not None:
            raise TooDeepError("Units have two levels; this one already sits under another.")
    await _check_name(units, body.name, body.parent_id)
    unit = Unit(name=body.name, parent_id=body.parent_id)
    async with transactions.run() as session:
        await units.insert_one(unit, session=session)
        await audit(entries, principal, request, action="unit.create", target_type="unit", target_id=unit.id,
                    meta={"name": unit.name, "parent_id": unit.parent_id}, session=session)  # fmt: skip
    return UnitOut(id=unit.id, name=unit.name, parent_id=unit.parent_id)


async def rename_unit(
    principal: Principal, unit_id: str, body: UnitRename, request: Request, *, units: TenantRepo[Unit],
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> UnitOut:  # fmt: skip
    require_admin(principal)
    unit = await units.find_one({"_id": unit_id})
    if unit is None:
        raise NotFoundError("This unit does not exist.")
    await _check_name(units, body.name, unit.parent_id, except_id=unit.id)
    async with transactions.run() as session:
        await units.update_one({"_id": unit.id}, {"$set": {"name": body.name}}, session=session)
        await audit(entries, principal, request, action="unit.rename", target_type="unit", target_id=unit.id,
                    meta={"before": unit.name, "after": body.name}, session=session)  # fmt: skip
    return UnitOut(id=unit.id, name=body.name, parent_id=unit.parent_id)


async def _check_units(units: TenantRepo[Unit], unit_ids: list[str]) -> list[str]:
    ordered = list(dict.fromkeys(unit_ids))  # keep the order (the first is the home unit), drop repeats
    if ordered and len(await units.find({"_id": {"$in": ordered}})) != len(ordered):
        raise UnknownUnitError("One or more units do not exist in your organisation.")
    return ordered


def _out(person: Person) -> PersonOut:
    return PersonOut(id=person.id, name=person.name, unit_id=person.unit_id, unit_ids=person.unit_ids)


async def create_person(
    principal: Principal, body: PersonIn, request: Request, *, people: TenantRepo[Person], units: TenantRepo[Unit],
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> PersonOut:  # fmt: skip
    require_admin(principal)
    person = Person(name=body.name, unit_ids=await _check_units(units, body.unit_ids))
    async with transactions.run() as session:
        await people.insert_one(person, session=session)
        await audit(entries, principal, request, action="person.create", target_type="person", target_id=person.id,
                    meta={"unit_ids": person.unit_ids}, session=session)  # fmt: skip
    return _out(person)


async def change_person(
    principal: Principal, person_id: str, body: PersonChange, request: Request, *, people: TenantRepo[Person],
    units: TenantRepo[Unit], entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> PersonOut:  # fmt: skip
    require_admin(principal)
    person = await people.find_one({"_id": person_id})
    if person is None:
        raise NotFoundError("This person does not exist.")
    changes: dict[str, object] = {}
    if body.name is not None and body.name != person.name:
        changes["name"] = body.name
    if body.unit_ids is not None:
        unit_ids = await _check_units(units, body.unit_ids)
        if unit_ids != person.unit_ids:
            changes["unit_ids"] = unit_ids
            changes["unit_id"] = unit_ids[0] if unit_ids else None
    if not changes:
        return _out(person)
    updated = person.model_copy(update=changes)
    async with transactions.run() as session:
        await people.update_one({"_id": person.id}, {"$set": changes}, session=session)
        await audit(entries, principal, request, action="person.update", target_type="person", target_id=person.id,
                    meta={k: v for k, v in changes.items() if k != "unit_id"}, session=session)  # fmt: skip
    return _out(updated)
