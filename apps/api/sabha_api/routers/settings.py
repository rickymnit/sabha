"""Workspace settings (sabha_api.services.settings, plan task P1.7)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from sabha_api.auth import Principal, require_role
from sabha_api.deps import Transactions, own_tenant_repo, tenant_repo, transactions
from sabha_api.services import settings as service
from sabha_core.models import AuditEntry
from sabha_core.repo import OwnTenantRepo, TenantRepo

router = APIRouter(prefix="/v1/settings", tags=["settings"])

Caller = Annotated[Principal, Depends(require_role(*service.ALLOWED))]
Own = Annotated[OwnTenantRepo, Depends(own_tenant_repo)]


@router.get("", response_model=service.SettingsOut)
async def read_settings(principal: Caller, tenant: Own) -> service.SettingsOut:
    """Your organisation's name, words and conversation types (owners and admins)."""
    return await service.read(tenant)


@router.patch("", response_model=service.SettingsOut)
async def update_settings(
    body: service.SettingsIn, request: Request, principal: Caller, tenant: Own,
    entries: Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))],
    txn: Annotated[Transactions, Depends(transactions)],
) -> service.SettingsOut:  # fmt: skip
    """Rename the organisation or its words, or switch conversation types on or off (owners and admins)."""
    return await service.update(principal, body, request, tenant_repo=tenant, entries=entries, transactions=txn)
