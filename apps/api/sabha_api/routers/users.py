"""Users: invites (plan task P1.5b). Logic in sabha_api.services.invites."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, Role, require_role
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import invites
from sabha_core.models import AuditEntry, IdempotencyRecord, IdentityLink, Unit, User
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("/invites", status_code=201, response_model=invites.InviteOut)
async def create_invite(
    body: invites.InviteIn,
    request: Request,
    principal: Annotated[Principal, Depends(require_role(Role.OWNER, Role.ADMIN))],
    records: Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))],
    users: Annotated[TenantRepo[User], Depends(tenant_repo("users", User))],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
    identities: Annotated[TenantRepo[IdentityLink], Depends(tenant_repo("identities", IdentityLink))],
    entries: Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))],
    txn: Annotated[Transactions, Depends(transactions)],
    idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:
    """Invite someone by email. Owners may invite any role; admins manager, reviewer and staff."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await invites.invite(
            principal,
            body,
            issuer=request.app.state.settings.oidc_issuer,
            users=users,
            units=units,
            identities=identities,
            entries=entries,
            request=request,
            transactions=txn,
        )
        return 201, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=invites.ROUTE, body=body, handler=handler)
