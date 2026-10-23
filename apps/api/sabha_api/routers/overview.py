"""GET /v1/overview (sabha_api.services.overview)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import overview as service
from sabha_core.models import Analysis, Person, Recording, Score
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/overview", tags=["overview"])


@router.get("", response_model=service.OverviewOut)
async def get_overview(
    principal: Annotated[Principal, Depends(current_principal)],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    scores: Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))],
    start: Annotated[datetime, Query(alias="from", description="Start of the period (UTC), included")],
    end: Annotated[datetime, Query(alias="to", description="End of the period (UTC), excluded; at most 366 days")],
) -> service.OverviewOut:
    """Numbers for the Overview page, for the recordings you may see: analysed recordings, audio hours and median
    scores in the period, the lowest-scoring rubric dimensions, and what is being processed right now."""
    return await service.overview(principal, start, end, people=people, recordings=recordings, analyses=analyses,
                                  scores=scores)  # fmt: skip
