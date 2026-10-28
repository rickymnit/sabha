"""Expected and actual cost in rupees (sabha_api.services.costs): GET /v1/costs/estimate and
GET /v1/recordings/{recording_id}/cost."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import costs as service
from sabha_core.models import Analysis, LlmCall, Person, Recording, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["costs"])

Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]


@router.get("/v1/costs/estimate", response_model=service.EstimateOut)
async def estimate(
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    recordings: Recordings,
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    type: ConversationType,
    duration_ms: Annotated[int, Query(ge=1, le=24 * 3_600_000)],
) -> service.EstimateOut:
    """What a recording of this type and length is expected to cost in rupees: speech-to-text at the published
    price, and the LLM at the median cost per minute of your organisation's recent recordings of the type. Parts
    without a price or history are null. Our own processing is not included."""
    settings = request.app.state.settings
    found = await service.estimate(type, duration_ms, settings, recordings=recordings, analyses=analyses)
    per_minute = found.total_inr / (duration_ms / 60_000) if found.total_inr is not None else None
    return service.EstimateOut(estimate=found, inr_per_minute=None if per_minute is None else round(per_minute, 4),
                               sources=service.sources(settings))  # fmt: skip


@router.get("/v1/recordings/{recording_id}/cost", response_model=service.CostOut)
async def recording_cost(
    recording_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    recordings: Recordings,
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    transcripts: Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))],
    llm_calls: Annotated[TenantRepo[LlmCall], Depends(tenant_repo("llm_calls", LlmCall))],
) -> service.CostOut:
    """The recording's expected cost (kept from upload) and its actual cost so far: speech-to-text audio sent and
    its price, and the LLM calls' recorded cost. `final` once the recording is finished."""
    return await service.recording_cost(principal, recording_id, request.app.state.settings, recordings=recordings,
                                        people=people, transcripts=transcripts, llm_calls=llm_calls)  # fmt: skip
