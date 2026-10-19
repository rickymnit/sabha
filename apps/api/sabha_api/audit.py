"""Writing the audit log (CLAUDE.md API conventions; plan task P1.8 adds reading it and the full action list).

`await audit(entries, principal, request, action=..., target_type=..., target_id=...)` appends one entry with the
actor, time, client address, user agent and request id. Entries are never updated or deleted. Pass the session to
write it in the same transaction as the change it records.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from pymongo.asynchronous.client_session import AsyncClientSession

from sabha_api.auth import Principal
from sabha_core.logging import request_id_var
from sabha_core.models import AuditEntry
from sabha_core.repo import TenantRepo


async def audit(
    entries: TenantRepo[AuditEntry],
    principal: Principal,
    request: Request,
    *,
    action: str,
    target_type: str,
    target_id: str,
    meta: Mapping[str, Any] | None = None,
    session: AsyncClientSession | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        request_id=request_id_var.get(),
        meta=dict(meta or {}),
    )
    return await entries.insert_one(entry, session=session)
