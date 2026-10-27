"""GET /v1/inbox (sabha_api.services.inbox)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import inbox as service
from sabha_core.models import Analysis, DeadLetter, Dispute, Person, Recording, Unit
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/inbox", tags=["inbox"])


@router.get("", response_model=service.InboxOut)
async def get_inbox(
    principal: Annotated[Principal, Depends(current_principal)],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    disputes: Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))],
    dlq: Annotated[TenantRepo[DeadLetter], Depends(tenant_repo("dlq", DeadLetter))],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
) -> service.InboxOut:
    """What waits for your decision, newest first: disputes you may decide, recordings to review, failed
    recordings to retry or close (owners and admins), and reception calls needing a follow-up (last 7 days). Empty
    when nothing waits."""
    return await service.inbox(principal, recordings=recordings, people=people, analyses=analyses,
                               disputes=disputes, dlq=dlq, units=units)  # fmt: skip
