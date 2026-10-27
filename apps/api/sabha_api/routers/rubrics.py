"""Reading rubrics (sabha_api.services.rubrics, plan task P6.8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.errors import NotFoundError
from sabha_api.services import rubrics as service
from sabha_core.models import Tenant

router = APIRouter(prefix="/v1/rubrics", tags=["rubrics"])

Caller = Annotated[Principal, Depends(current_principal)]
Found = Annotated[Directory, Depends(directory)]


async def _tenant(principal: Principal, found: Directory) -> Tenant:
    tenant = await found.tenant(principal.tenant_id)
    if tenant is None:
        raise NotFoundError("Your organisation could not be found.")
    return tenant


@router.get("", response_model=service.RubricList)
async def list_rubrics(request: Request, principal: Caller, found: Found) -> service.RubricList:
    """The rubric in use for each of your organisation's conversation types, with its versions."""
    return service.list_rubrics(await _tenant(principal, found), request.app.state.settings.rubrics_dir)


@router.get("/{rubric_id}", response_model=service.RubricOut)
async def read_rubric(rubric_id: str, request: Request, principal: Caller, found: Found) -> service.RubricOut:
    """One rubric: its dimensions and scale, its versions and what changed from the version before."""
    return service.read_rubric(await _tenant(principal, found), rubric_id, request.app.state.settings.rubrics_dir)
