"""GET /v1/me: the signed-in user, their role and units, and their tenant's labels (plan task P1.5b)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sabha_api.auth import Principal, Role, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import tenant_repo
from sabha_api.errors import NotFoundError
from sabha_core.models import Unit, User
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["me"])


class MeUser(BaseModel):
    id: str
    email: str
    name: str
    role: Role
    title: str | None  # job title, display only
    unit_ids: list[str]


class MeUnit(BaseModel):
    id: str
    name: str
    parent_id: str | None = None  # the unit it sits under (a section's class); None for a top-level unit


class MeTenant(BaseModel):
    id: str
    name: str
    profile: str
    labels: dict[str, str]  # the UI's nouns (CLAUDE.md: never hard-code "Teacher" or "Lesson")
    enabled_types: list[str]
    units: list[MeUnit]  # every unit's name, so lists can say "Class 6" rather than an id


class Me(BaseModel):
    user: MeUser
    tenant: MeTenant


@router.get("/v1/me", response_model=Me)
async def me(
    principal: Annotated[Principal, Depends(current_principal)],
    users: Annotated[TenantRepo[User], Depends(tenant_repo("users", User))],
    found: Annotated[Directory, Depends(directory)],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
) -> Me:
    user = await users.find_one({"_id": principal.user_id})
    tenant = await found.tenant(principal.tenant_id)
    if user is None or tenant is None:
        raise NotFoundError("Your account could not be found.")
    return Me(
        user=MeUser(
            id=user.id, email=user.email, name=user.name, role=user.role, title=user.title, unit_ids=user.unit_ids
        ),
        tenant=MeTenant(
            id=tenant.id,
            name=tenant.name,
            profile=tenant.profile,
            labels=tenant.labels.model_dump(),
            enabled_types=[t.value for t in tenant.enabled_types],
            units=[
                MeUnit(id=u.id, name=u.name, parent_id=u.parent_id) for u in await units.find({}, sort=[("name", 1)])
            ],
        ),
    )
