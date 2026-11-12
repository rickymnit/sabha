"""Approved product information (sabha_api.services.product_info)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import product_info as service
from sabha_core.models import AuditEntry, IdempotencyRecord, ProductInfo
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/product-info", tags=["product information"])

Caller = Annotated[Principal, Depends(current_principal)]
Entries = Annotated[TenantRepo[ProductInfo], Depends(tenant_repo("product_info", ProductInfo))]
Log = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]


@router.get("", response_model=service.ProductInfoList)
async def list_product_info(principal: Caller, entries: Entries,
                            include_retired: bool = False) -> service.ProductInfoList:  # fmt: skip
    """The approved product information, by title. Everyone signed in sees the active entries; owners and admins
    may include retired ones. `can_edit` says whether the caller may change them."""
    return await service.list_entries(principal, entries=entries, include_retired=include_retired)


@router.post("", status_code=201, response_model=service.ProductInfoOut)
async def create_product_info(
    body: service.ProductInfoIn, request: Request, principal: Caller, entries: Entries, log: Log, records: Records,
    txn: Txn, idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:  # fmt: skip
    """Add an approved entry (title and text). Owners and admins; at most 40 active. Audited."""

    async def handler() -> tuple[int, dict[str, object]]:
        created = await service.create(principal, body, request, entries=entries, log=log, transactions=txn)
        return 201, created.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.ROUTE, body=body, handler=handler)


@router.patch("/{entry_id}", response_model=service.ProductInfoOut)
async def change_product_info(entry_id: str, body: service.ProductInfoChange, request: Request, principal: Caller,
                              entries: Entries, log: Log, txn: Txn) -> service.ProductInfoOut:  # fmt: skip
    """Change an entry's title or text, or retire it (status "retired") or bring it back. Owners and admins.
    Audited."""
    return await service.change(principal, entry_id, body, request, entries=entries, log=log, transactions=txn)
