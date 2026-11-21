"""Models and usage (sabha_api.services.models_usage): GET /v1/models-usage."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from sabha_api.auth import Principal, require_role
from sabha_api.deps import tenant_repo
from sabha_api.services import models_usage as service
from sabha_core.models import LlmCall, Transcript
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["usage"])


@router.get("/v1/models-usage", response_model=service.ModelsUsageOut)
async def models_usage(
    request: Request,
    principal: Annotated[Principal, Depends(require_role(*service.ALLOWED))],
    transcripts: Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))],
    llm_calls: Annotated[TenantRepo[LlmCall], Depends(tenant_repo("llm_calls", LlmCall))],
) -> service.ModelsUsageOut:
    """The last 30 days of AI model use and cost, and the credit left where the provider reports it (owners, admins)."""
    return await service.summary(request.app.state.settings, transcripts, llm_calls)
