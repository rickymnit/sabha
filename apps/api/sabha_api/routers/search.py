"""GET /v1/search (sabha_api.services.search)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import search as service
from sabha_core.models import Analysis, Person, Recording, Transcript
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/search", tags=["search"])


@router.get("", response_model=service.SearchOut)
async def search(
    principal: Annotated[Principal, Depends(current_principal)],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    transcripts: Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))],
    q: Annotated[str, Query(min_length=service.MIN_LENGTH, max_length=service.MAX_LENGTH)],
) -> service.SearchOut:
    """People and recordings whose name contains `q` (any case), a few of each, from what you may see. Names only:
    what was said in a recording is not searched."""
    return await service.search(principal, q, people=people, recordings=recordings, analyses=analyses,
                                transcripts=transcripts)  # fmt: skip
