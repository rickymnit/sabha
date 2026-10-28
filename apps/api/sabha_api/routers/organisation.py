"""Units and people for owners and admins (sabha_api.services.organisation)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import organisation as service
from sabha_core.models import AuditEntry, IdempotencyRecord, Person, Unit
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["organisation"])

Caller = Annotated[Principal, Depends(current_principal)]
Units = Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]
Key = Annotated[str | None, Header(alias=HEADER)]


@router.post("/v1/units", status_code=201, response_model=service.UnitOut)
async def create_unit(body: service.UnitIn, request: Request, principal: Caller, units: Units, entries: Entries,
                      records: Records, txn: Txn, idempotency_key: Key = None) -> JSONResponse:  # fmt: skip
    """Add a top-level unit (a school's class) or, with parent_id, one under it (a section). Owners and admins."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.create_unit(principal, body, request, units=units, entries=entries, transactions=txn)
        return 201, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.UNIT_ROUTE, body=body, handler=handler)


@router.patch("/v1/units/{unit_id}", response_model=service.UnitOut)
async def rename_unit(unit_id: str, body: service.UnitRename, request: Request, principal: Caller, units: Units,
                      entries: Entries, txn: Txn) -> service.UnitOut:  # fmt: skip
    """Rename a unit. Owners and admins."""
    return await service.rename_unit(principal, unit_id, body, request, units=units, entries=entries, transactions=txn)


@router.post("/v1/people", status_code=201, response_model=service.PersonOut)
async def create_person(
    body: service.PersonIn, request: Request, principal: Caller, people: People, units: Units, entries: Entries,
    records: Records, txn: Txn, idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Add a person who is analysed (a school's teacher) with the units they work in; no login. Owners and admins."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.create_person(principal, body, request, people=people, units=units, entries=entries,
                                          transactions=txn)  # fmt: skip
        return 201, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.PERSON_ROUTE, body=body, handler=handler)


@router.patch("/v1/people/{person_id}", response_model=service.PersonOut)
async def change_person(person_id: str, body: service.PersonChange, request: Request, principal: Caller,
                        people: People, units: Units, entries: Entries, txn: Txn) -> service.PersonOut:  # fmt: skip
    """Rename a person or change the units they work in (the first is their home unit). Owners and admins."""
    return await service.change_person(principal, person_id, body, request, people=people, units=units,
                                       entries=entries, transactions=txn)  # fmt: skip
