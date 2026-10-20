"""Inviting users (plan task P1.5b). An invite creates the user (status "invited") and the pending identity link that
their first login claims (sabha_api.auth.directory), in one transaction.

Who may invite whom: owners any role; admins manager, reviewer and staff, so no admin can create an admin or an
owner (decided 2026-10-19). Units must belong to the inviter's tenant. One user per email per tenant.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pymongo.errors import DuplicateKeyError

from sabha_api.auth import Principal
from sabha_api.deps import Transactions
from sabha_api.errors import ApiError, ConflictError, ForbiddenError
from sabha_core.models import Email, IdentityLink, Role, Unit, User
from sabha_core.repo import TenantRepo

ROUTE = "POST /v1/users/invites"

MAY_INVITE: dict[Role, frozenset[Role]] = {
    Role.OWNER: frozenset(Role),
    Role.ADMIN: frozenset({Role.MANAGER, Role.REVIEWER, Role.STAFF}),
}


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no id, tenant_id or status from clients

    email: Email
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    role: Role
    unit_ids: list[str] = Field(default_factory=list, max_length=100)


class InviteOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: Role
    unit_ids: list[str]
    status: str


class RoleNotAllowedError(ForbiddenError):
    code, title = "role_not_allowed", "Role not allowed"


class UserExistsError(ConflictError):
    code, title = "user_exists", "User exists"


class UnknownUnitError(ApiError):
    status, code, title = 422, "unknown_unit", "Unknown unit"


async def invite(
    principal: Principal,
    body: InviteIn,
    *,
    issuer: str,
    users: TenantRepo[User],
    units: TenantRepo[Unit],
    identities: TenantRepo[IdentityLink],
    transactions: Transactions,
) -> InviteOut:
    if body.role not in MAY_INVITE.get(principal.role, frozenset()):
        raise RoleNotAllowedError(f"A {principal.role} cannot invite a {body.role}.")
    unit_ids = list(dict.fromkeys(body.unit_ids))
    if unit_ids and await units.count({"_id": {"$in": unit_ids}}) != len(unit_ids):
        raise UnknownUnitError("One or more units do not exist in your organisation.")
    if await users.find_one({"email": body.email}) is not None:
        raise UserExistsError("A user with this email already exists in your organisation.")
    user = User(email=body.email, name=body.name, role=body.role, unit_ids=unit_ids, status="invited")
    try:
        async with transactions.run() as session:
            user = await users.insert_one(user, session=session)
            await identities.insert_one(IdentityLink(issuer=issuer, email=body.email, user_id=user.id), session=session)
    except DuplicateKeyError as exc:  # a concurrent invite for the same email won
        raise UserExistsError("A user with this email already exists in your organisation.") from exc
    return InviteOut(
        user_id=user.id, email=user.email, name=user.name, role=user.role, unit_ids=user.unit_ids, status=user.status
    )
