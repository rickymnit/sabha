"""The signed-in person's own workspace (sabha_api.services.workspace)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from sabha_analytics.rubric import Rubric
from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import tenant_repo
from sabha_api.services import workspace as service
from sabha_api.services.rubrics import current_rubric
from sabha_core.models import Analysis, Person, Recording, Score
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/me", tags=["my workspace"])

Caller = Annotated[Principal, Depends(current_principal)]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Scores = Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))]
Found = Annotated[Directory, Depends(directory)]


async def _sales_rubric(request: Request, principal: Principal, found: Directory) -> Rubric | None:
    tenant = await found.tenant(principal.tenant_id)
    if tenant is None:
        return None
    return current_rubric(tenant, ConversationType.SALES, request.app.state.settings.rubrics_dir)


@router.get("/next-actions", response_model=service.NextActionList)
async def my_next_actions(request: Request, principal: Caller, found: Found, people: People, recordings: Recordings,
                          analyses: Analyses) -> service.NextActionList:  # fmt: skip
    """Your own next actions from your sales calls and meetings of the last 60 days: what was agreed, with whom,
    the date as said and the date it means, and a priority (high, medium, low), highest first. Empty if no person is
    linked to you."""
    rubric = await _sales_rubric(request, principal, found)
    return await service.next_actions(principal, people=people, recordings=recordings, analyses=analyses,
                                      rubric=rubric)  # fmt: skip


@router.get("/summary", response_model=service.Summary)
async def my_summary(principal: Caller, people: People, recordings: Recordings, analyses: Analyses,
                     period: Literal["week", "month"] = "week") -> service.Summary:  # fmt: skip
    """Your sales calls, meetings and both together this week or month (Asia/Kolkata) and the one before, with the
    average overall score of the finished ones. Zeros if no person is linked to you."""
    return await service.summary(principal, period, people=people, recordings=recordings, analyses=analyses)


@router.get("/coaching", response_model=service.CoachingOut)
async def my_coaching(request: Request, principal: Caller, found: Found, people: People, recordings: Recordings,
                      analyses: Analyses, scores: Scores) -> service.CoachingOut:  # fmt: skip
    """Your private coaching: your average score per coaching theme over the last 30 days and the 30 before, the
    theme to focus on, and your practice points from each call and meeting, newest first. Only you see this."""
    rubric = await _sales_rubric(request, principal, found)
    return await service.coaching(principal, people=people, recordings=recordings, analyses=analyses, scores=scores,
                                  rubric=rubric)  # fmt: skip
