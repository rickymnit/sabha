"""The signed-in person's own workspace (sabha_api.services.workspace)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import tenant_repo
from sabha_api.services import workspace as service
from sabha_api.services.rubrics import current_rubric
from sabha_core.models import Analysis, Person, Recording
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/me", tags=["my workspace"])

Caller = Annotated[Principal, Depends(current_principal)]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Found = Annotated[Directory, Depends(directory)]


@router.get("/next-actions", response_model=service.NextActionList)
async def my_next_actions(request: Request, principal: Caller, found: Found, people: People, recordings: Recordings,
                          analyses: Analyses) -> service.NextActionList:  # fmt: skip
    """Your own next actions from your sales calls and meetings of the last 60 days: what was agreed, with whom,
    the date as said and the date it means, and a priority (high, medium, low), highest first. Empty if no person is
    linked to you."""
    tenant = await found.tenant(principal.tenant_id)
    rubric = None if tenant is None else current_rubric(tenant, ConversationType.SALES,
                                                        request.app.state.settings.rubrics_dir)  # fmt: skip
    return await service.next_actions(principal, people=people, recordings=recordings, analyses=analyses,
                                      rubric=rubric)  # fmt: skip
