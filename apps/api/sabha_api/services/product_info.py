"""Approved product information (founder's Sales Executive dashboard doc, 2026-11-12).

AI coaching and product-related suggestions use only this information, so the AI never states unsupported product
facts to a rep. Rules:

- Everyone signed in may read the active entries (GET /v1/product-info): reps review what coaching points them to.
  Owners and admins may also list retired ones (?include_retired=true).
- Only owners and admins (the doc's Super Admin) add (POST) and change (PATCH title, body or status) entries;
  managers, reviewers and staff get 403 `not_allowed`. Every change is audited.
- At most MAX_ACTIVE active entries per tenant (422 `product_info_limit`), so the coaching prompt stays small.
- Retiring keeps the entry (status "retired"): it is no longer given to the AI, but coaching that already points at
  it can still show it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, ForbiddenError, NotFoundError
from sabha_core.models import PRODUCT_INFO_BODY_MAX, PRODUCT_INFO_TITLE_MAX, AuditEntry, ProductInfo, utc_now
from sabha_core.repo import TenantRepo

ROUTE = "POST /v1/product-info"
EDITORS = frozenset({Role.OWNER, Role.ADMIN})
MAX_ACTIVE = 40

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PRODUCT_INFO_TITLE_MAX)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PRODUCT_INFO_BODY_MAX)]


class ProductInfoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    body: Body


class ProductInfoChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    body: Body | None = None
    status: Literal["active", "retired"] | None = None


class ProductInfoOut(BaseModel):
    id: str
    title: str
    body: str
    status: Literal["active", "retired"]
    updated_at: datetime


class ProductInfoList(BaseModel):
    items: list[ProductInfoOut]
    can_edit: bool


class NotAllowedError(ForbiddenError):
    code, title = "not_allowed", "Not allowed"


class ProductInfoLimitError(ApiError):
    status, code, title = 422, "product_info_limit", "Too many entries"


def out(entry: ProductInfo) -> ProductInfoOut:
    return ProductInfoOut(id=entry.id, title=entry.title, body=entry.body, status=entry.status,
                          updated_at=entry.updated_at)  # fmt: skip


def _require_editor(principal: Principal) -> None:
    if principal.role not in EDITORS:
        raise NotAllowedError("Only owners and admins change the approved product information.")


async def _check_room(entries: TenantRepo[ProductInfo]) -> None:
    if len(await entries.find({"status": "active"}, limit=MAX_ACTIVE)) >= MAX_ACTIVE:
        raise ProductInfoLimitError(f"At most {MAX_ACTIVE} entries can be active. Retire one first.")


async def list_entries(
    principal: Principal, *, entries: TenantRepo[ProductInfo], include_retired: bool
) -> ProductInfoList:
    editor = principal.role in EDITORS
    query = {} if include_retired and editor else {"status": "active"}
    found = await entries.find(query, sort=[("title", 1)], limit=200)
    return ProductInfoList(items=[out(e) for e in found], can_edit=editor)


async def create(
    principal: Principal, body: ProductInfoIn, request: Request, *, entries: TenantRepo[ProductInfo],
    log: TenantRepo[AuditEntry], transactions: Transactions,
) -> ProductInfoOut:  # fmt: skip
    _require_editor(principal)
    await _check_room(entries)
    entry = ProductInfo(title=body.title, body=body.body, created_by=principal.user_id, updated_by=principal.user_id)
    async with transactions.run() as session:
        await entries.insert_one(entry, session=session)
        await audit(log, principal, request, action="product_info.create", target_type="product_info",
                    target_id=entry.id, meta={"title": entry.title}, session=session)  # fmt: skip
    return out(entry)


async def change(
    principal: Principal, entry_id: str, body: ProductInfoChange, request: Request, *,
    entries: TenantRepo[ProductInfo], log: TenantRepo[AuditEntry], transactions: Transactions,
) -> ProductInfoOut:  # fmt: skip
    _require_editor(principal)
    entry = await entries.find_one({"_id": entry_id})
    if entry is None:
        raise NotFoundError("This product information does not exist.")
    changes = body.model_dump(exclude_none=True)
    if changes.get("status") == "active" and entry.status != "active":
        await _check_room(entries)
    updated = entry.model_copy(update={**changes, "updated_by": principal.user_id, "updated_at": utc_now()})
    async with transactions.run() as session:
        await entries.update_one({"_id": entry.id}, {"$set": {**changes, "updated_by": updated.updated_by,
                                                              "updated_at": updated.updated_at}},
                                 session=session)  # fmt: skip
        await audit(log, principal, request, action="product_info.update", target_type="product_info",
                    target_id=entry.id, meta={"fields": sorted(changes)}, session=session)  # fmt: skip
    return out(updated)
