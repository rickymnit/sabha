"""The audit log (sabha_api.services.audit_log, plan task P1.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from sabha_api.auth import Principal, require_role
from sabha_api.deps import tenant_repo
from sabha_api.services import audit_log as service
from sabha_core.models import AuditEntry, Dispute, Person, Recording, Unit, User
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["audit"])


@router.get("/v1/audit", response_model=service.AuditPage)
async def list_audit(
    principal: Annotated[Principal, Depends(require_role(*service.ALLOWED))],
    entries: Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))],
    users: Annotated[TenantRepo[User], Depends(tenant_repo("users", User))],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    disputes: Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = 50,
    action: str | None = None,
    actor_user_id: str | None = None,
    target_id: str | None = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> service.AuditPage:
    """Who did what, newest first (owners and admins): playback, report views, disputes, reviews, re-analysis,
    settings changes, invites, and changes to people and units. Filter by action, person, target or time; page with
    `cursor`."""
    return await service.list_entries(entries=entries, users=users, recordings=recordings, disputes=disputes,
                                      people=people, units=units,
                                      cursor=cursor, limit=limit, action=action, actor_user_id=actor_user_id,
                                      target_id=target_id, since=since, until=until)  # fmt: skip
