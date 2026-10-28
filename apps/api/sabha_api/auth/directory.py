"""The user directory: who a login is, across tenants (plan task P1.5b, ADR 0002).

This is the one place in the API that reads before the tenant is known, so it is the only API module allowed to
use SystemRepo (tests/security/test_raw_collection_access.py). Everything after the lookup is tenant-scoped.

Login (`principal_for`):
1. A login already linked: the `identities` record with this (issuer, subject) names the tenant and user.
2. A first login: the verified email from the provider's userinfo endpoint finds the pending invite (subject not
   yet set). It is linked to this subject and the user becomes active. Unverified or missing email: 403
   `email_not_verified`. Pending invites from more than one tenant: 403 `ambiguous_invite` (a login links to one
   tenant; we never choose for the user). No invite: None, which the caller turns into 403 `not_invited`.
3. A disabled user: 403 `user_disabled`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from sabha_api.auth.oidc import Identity, TokenVerifier
from sabha_api.auth.principal import Principal
from sabha_api.errors import ForbiddenError, NotReadyError
from sabha_core.models import IdentityLink, Tenant, Unit, User
from sabha_core.repo import SystemRepo, TenantRepo
from sabha_core.units import subtree


class EmailNotVerifiedError(ForbiddenError):
    code, title = "email_not_verified", "Email not verified"


class AmbiguousInviteError(ForbiddenError):
    code, title = "ambiguous_invite", "Invites from more than one organisation"


class UserDisabledError(ForbiddenError):
    code, title = "user_disabled", "Account disabled"


class Directory:
    def __init__(self, db: AsyncDatabase[dict[str, Any]], verifier: TokenVerifier) -> None:
        self._db = db
        self._verifier = verifier
        self._identities = SystemRepo(db, "identities", IdentityLink)
        self._tenants = SystemRepo(db, "tenants", Tenant)

    async def principal_for(self, identity: Identity, access_token: str) -> Principal | None:
        link = await self._linked(identity)
        if link is None:
            link = await self._link_invite(identity, access_token)
            if link is None:
                return None
        users = TenantRepo(self._db, "users", link.tenant_id, User)
        user = await users.find_one({"_id": link.user_id})
        if user is None:
            return None
        if user.status == "disabled":
            raise UserDisabledError("Your account has been disabled. Ask your administrator.")
        if user.status == "invited":
            await users.update_one({"_id": user.id, "status": "invited"}, {"$set": {"status": "active"}})
        unit_ids = user.unit_ids
        if unit_ids:  # a manager of "Class 6" also manages its sections, wherever access is checked
            units = TenantRepo(self._db, "units", link.tenant_id, Unit)
            unit_ids = sorted(subtree(await units.find({}), unit_ids))
        return Principal(user_id=user.id, tenant_id=link.tenant_id, role=user.role, unit_ids=tuple(unit_ids))

    async def tenant(self, tenant_id: str) -> Tenant | None:
        return await self._tenants.find_one({"_id": tenant_id})

    async def _linked(self, identity: Identity) -> IdentityLink | None:
        return await self._identities.find_one({"issuer": identity.issuer, "subject": identity.subject})

    async def _link_invite(self, identity: Identity, access_token: str) -> IdentityLink | None:
        email = await self._verifier.verified_email(access_token)
        if email is None:
            raise EmailNotVerifiedError("Sign in with an account whose email address is verified.")
        pending = await self._identities.find(
            {"issuer": identity.issuer, "email": email.strip().lower(), "subject": None}
        )
        if not pending:
            return None
        if len({link.tenant_id for link in pending}) > 1:
            raise AmbiguousInviteError(
                "You have invites from more than one organisation. Ask one of them to withdraw theirs."
            )
        invite = pending[0]  # one per tenant: identities has a unique (tenant_id, email) index
        try:
            matched = await self._identities.update_one(
                {"_id": invite.id, "subject": None}, {"$set": {"subject": identity.subject}}
            )
        except DuplicateKeyError:
            matched = 0  # a concurrent request linked this login first
        if matched == 0:
            return await self._linked(identity)
        return invite.model_copy(update={"subject": identity.subject})


def directory(request: Request) -> Directory:
    found: Directory | None = getattr(request.app.state, "directory", None)
    if found is None:
        raise NotReadyError("The user directory is not available yet.")
    return found
