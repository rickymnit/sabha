"""GET /v1/me: the signed-in user, their role and units, and their tenant's labels (plan task P1.5b)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sabha_api.auth import Principal, Role, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import tenant_repo
from sabha_api.errors import NotFoundError
from sabha_core.models import User
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["me"])


class MeUser(BaseModel):
    id: str
    email: str
    name: str
    role: Role
    unit_ids: list[str]


class MeTenant(BaseModel):
    id: str
    name: str
    profile: str
    labels: dict[str, str]  # the UI's nouns (CLAUDE.md: never hard-code "Teacher" or "Lesson")
    enabled_types: list[str]


class Me(BaseModel):
    user: MeUser
    tenant: MeTenant


@router.get("/v1/me", response_model=Me)
async def me(
    principal: Annotated[Principal, Depends(current_principal)],
    users: Annotated[TenantRepo[User], Depends(tenant_repo("users", User))],
    found: Annotated[Directory, Depends(directory)],
) -> Me:
    user = await users.find_one({"_id": principal.user_id})
    tenant = await found.tenant(principal.tenant_id)
    if user is None or tenant is None:
        raise NotFoundError("Your account could not be found.")
    return Me(
        user=MeUser(id=user.id, email=user.email, name=user.name, role=user.role, unit_ids=user.unit_ids),
        tenant=MeTenant(
            id=tenant.id,
            name=tenant.name,
            profile=tenant.profile,
            labels=tenant.labels.model_dump(),
            enabled_types=[t.value for t in tenant.enabled_types],
        ),
    )
