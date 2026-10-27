"""GET /v1/overview (sabha_api.services.overview)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import overview as service
from sabha_core.models import Analysis, Person, Recording, Score, Unit
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/overview", tags=["overview"])


@router.get("", response_model=service.OverviewOut)
async def get_overview(
    principal: Annotated[Principal, Depends(current_principal)],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    scores: Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
    start: Annotated[datetime, Query(alias="from", description="Start of the period (UTC), included")],
    end: Annotated[datetime, Query(alias="to", description="End of the period (UTC), excluded; at most 366 days")],
    unit_id: Annotated[str | None, Query(description="Only this unit and the units under it")] = None,
) -> service.OverviewOut:
    """Numbers for the Overview page, for the recordings you may see (narrowed to one unit with `unit_id`):
    analysed recordings, audio and silence hours, median scores and reception tickets in the period and the seven
    periods before it, the lowest-scoring rubric dimensions by unit and week, and what is being processed now."""
    return await service.overview(principal, start, end, unit_id=unit_id, people=people, recordings=recordings,
                                  analyses=analyses, scores=scores, units=units)  # fmt: skip
