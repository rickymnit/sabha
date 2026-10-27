"""This month's audio hours (sabha_api.services.usage, plan tasks P6.2 and P7.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from sabha_api.auth import Principal, require_role
from sabha_api.deps import own_tenant_repo, tenant_repo
from sabha_api.errors import NotFoundError
from sabha_api.services import usage as service
from sabha_core.models import Recording
from sabha_core.repo import OwnTenantRepo, TenantRepo

router = APIRouter(tags=["usage"])


@router.get("/v1/usage", response_model=service.UsageOut)
async def usage(
    principal: Annotated[Principal, Depends(require_role(*service.ALLOWED))],
    own: Annotated[OwnTenantRepo, Depends(own_tenant_repo)],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
) -> service.UsageOut:
    """This month's audio hours against the plan's allowance (owners and admins)."""
    tenant = await own.get()
    if tenant is None:
        raise NotFoundError("Your organisation could not be found.")
    return await service.summary(tenant, recordings)
