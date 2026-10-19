"""Who is calling: the principal behind a request, and role checks (plan task P1.5).

`current_principal` turns `Authorization: Bearer <token>` into a Principal:
token → TokenVerifier (sabha_api.auth.oidc) → Identity (issuer, subject) → PrincipalStore → Principal.

- No token, or an invalid one: 401 `unauthorized`.
- A valid token for an identity that no tenant has invited: 403 `not_invited`. First login creates nothing.

`require_role(*roles)` builds a dependency that also answers 403 `forbidden` to every other role. There is no implied
hierarchy: each route lists every role it allows, so adding a role never widens access by accident.

The store is a Protocol. P1.5b backs it with the `identities` system collection (issuer, subject → tenant, user; see
ADR 0002) and the tenant-scoped `users` collection; until then the app has no store and protected routes answer 503.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sabha_api.auth.oidc import Identity, TokenVerifier
from sabha_api.errors import ForbiddenError, NotReadyError, UnauthorizedError
from sabha_core.models import Role


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    tenant_id: str
    role: Role
    unit_ids: tuple[str, ...]


class PrincipalStore(Protocol):
    async def principal_for(self, identity: Identity) -> Principal | None:
        """The user this identity is linked to, or None if no tenant has invited it."""
        ...


class NotInvitedError(ForbiddenError):
    code, title = "not_invited", "Not invited"


_bearer = HTTPBearer(auto_error=False, description="Access token from the identity provider (ADR 0002)")


async def current_principal(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Principal:
    if credentials is None:
        raise UnauthorizedError("Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    verifier: TokenVerifier = request.app.state.token_verifier
    identity = await verifier.verify(credentials.credentials)
    store: PrincipalStore | None = request.app.state.principals
    if store is None:
        raise NotReadyError("The user directory is not available yet.")
    principal = await store.principal_for(identity)
    if principal is None:
        raise NotInvitedError("Your account has not been invited. Ask your administrator for an invite.")
    return principal


def require_role(*roles: Role) -> Callable[..., Awaitable[Principal]]:
    """A dependency returning the principal if their role is one of `roles`, else 403 `forbidden`."""
    if not roles:
        raise ValueError("name at least one role")
    allowed = frozenset(roles)

    async def dependency(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if principal.role not in allowed:
            raise ForbiddenError("Your role does not allow this.")
        return principal

    return dependency
