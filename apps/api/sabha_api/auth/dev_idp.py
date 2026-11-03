"""A local sign-in for development while Auth0 is not set up (decided 2026-10-22; Auth0 replaces it later).

Only when APP_ENV=local and DEV_LOGIN=true (settings refuse DEV_LOGIN anywhere else, and the routes are not mounted
without it). It is a tiny identity provider inside the API:

- a fresh RS256 key per process (restarting the API signs everyone out);
- `GET /dev-idp/users`: the people who can sign in, from the identities linked to this issuer (seeded by
  `scripts/admin/dev_seed.py`), with their tenant, role and name, for the web app's "Sign in as..." list;
- `POST /dev-idp/token {subject}`: a signed access token for one of them (8 hours).

Tenants whose id starts with HIDDEN_TENANT_PREFIX (the browser tests' "E2E School") are left out of the list, so
the demo sign-in page shows only the demo school; their people can still get a token by subject.

Tokens are checked by the normal TokenVerifier (signature, issuer, audience, expiry) through `fetch`, which serves
the discovery document and JWKS from memory, so nothing about authorisation is bypassed: the API still finds the
user, tenant and role from its own records. The routes are left out of the OpenAPI document.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections.abc import Mapping
from typing import Annotated, Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from sabha_api.auth.oidc import TokenVerifier
from sabha_api.auth.password import verify_password
from sabha_api.deps import _database
from sabha_api.errors import NotFoundError, UnauthorizedError
from sabha_core.models import IdentityLink, Tenant, User
from sabha_core.repo import SystemRepo, TenantRepo

log = logging.getLogger(__name__)

TOKEN_TTL_S = 8 * 3600
HIDDEN_TENANT_PREFIX = "e2e-"
KID = "dev-1"


class DevIdp:
    def __init__(self, issuer: str, audience: str) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def fetch(self, url: str) -> Mapping[str, Any]:
        if url == f"{self.issuer}/.well-known/openid-configuration":
            return {"issuer": self.issuer, "jwks_uri": f"{self.issuer}/jwks"}
        if url == f"{self.issuer}/jwks":
            entry = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
            return {"keys": [{**entry, "kid": KID, "use": "sig", "alg": "RS256"}]}
        raise httpx.ConnectError(url)

    def token(self, subject: str, email: str) -> str:
        now = int(time.time())
        claims = {"iss": self.issuer, "aud": self.audience, "sub": subject, "email": email, "email_verified": True,
                  "iat": now, "exp": now + TOKEN_TTL_S}  # fmt: skip
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": KID})

    def ticket(self, subject: str, ttl_s: int) -> str:
        """A short-lived proof of a password sign-in, for choosing an organisation. Its audience is not the API's, so
        the TokenVerifier never accepts it as an access token."""
        now = int(time.time())
        claims = {"iss": self.issuer, "aud": self._ticket_audience, "sub": subject, "iat": now, "exp": now + ttl_s}
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": KID})

    def ticket_is_valid(self, ticket: str) -> bool:
        try:
            jwt.decode(ticket, self._key.public_key(), algorithms=["RS256"], audience=self._ticket_audience,
                       issuer=self.issuer, options={"require": ["exp", "sub"]})  # fmt: skip
        except jwt.PyJWTError:
            return False
        return True

    @property
    def _ticket_audience(self) -> str:
        return f"{self.audience}:choose-organisation"

    def verifier(self) -> TokenVerifier:
        return TokenVerifier(self.issuer, self.audience, fetch=self.fetch)


class DevUser(BaseModel):
    subject: str
    name: str
    title: str | None
    email: str
    role: str
    tenant_id: str
    tenant_name: str


class TokenIn(BaseModel):
    subject: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105  # the OAuth token type, not a secret
    expires_in: int = TOKEN_TTL_S


router = APIRouter(prefix="/dev-idp", tags=["dev"], include_in_schema=False)
Db = Annotated[AsyncDatabase[dict[str, Any]], Depends(_database)]


def _idp(request: Request) -> DevIdp:
    idp: DevIdp = request.app.state.dev_idp
    return idp


async def _users(db: AsyncDatabase[dict[str, Any]], issuer: str) -> list[tuple[IdentityLink, User, Tenant]]:
    identities = SystemRepo(db, "identities", IdentityLink)
    tenant_repo = SystemRepo(db, "tenants", Tenant)
    links = await identities.find({"issuer": issuer, "subject": {"$ne": None}})
    tenants = {t.id: t for t in await tenant_repo.find({})}
    out = []
    for link in links:
        users = TenantRepo(db, "users", link.tenant_id, User)
        user = await users.find_one({"_id": link.user_id})
        if user is not None and user.status == "active" and link.tenant_id in tenants and link.subject:
            out.append((link, user, tenants[link.tenant_id]))
    return sorted(out, key=lambda row: (row[2].name, row[1].role, row[1].name))


@router.get("/users", response_model=list[DevUser])
async def users(request: Request, db: Db) -> list[DevUser]:
    idp = _idp(request)
    return [
        DevUser(subject=link.subject or "", name=user.name, title=user.title, email=user.email, role=user.role,
                tenant_id=tenant.id, tenant_name=tenant.name)
        for link, user, tenant in await _users(db, idp.issuer)
        if not tenant.id.startswith(HIDDEN_TENANT_PREFIX)
    ]  # fmt: skip


@router.post("/token", response_model=TokenOut)
async def token(body: TokenIn, request: Request, db: Db) -> TokenOut:
    idp = _idp(request)
    for link, user, _ in await _users(db, idp.issuer):
        if link.subject == body.subject:
            return TokenOut(access_token=idp.token(body.subject, user.email))
    raise NotFoundError("No one with that sign-in exists here; run scripts/admin/dev_seed.py.")


# --- Local password sign-in (owner's choice, 2026-10-28) ---
#
# One username and password from .env (LOGIN_USERNAME, LOGIN_PASSWORD_HASH), signing in as a Sabha user named in
# LOGIN_AS. APP_ENV=local only (settings), and never with the "Sign in as..." list above, which would skip the
# password: when this is on, only /auth/... is mounted. The token is the same as the dev sign-in's, so the API still
# finds the user, tenant and role from its own records.
#
# LOGIN_AS may list several emails, one per organisation (2026-11-02). With one, /auth/login returns the token. With
# more, it returns the organisations and a short-lived ticket (signed by the same key, its own audience so it is never
# accepted as an access token); the web app shows a picker and trades the ticket for a token at /auth/organisation.

TICKET_TTL_S = 5 * 60


class LoginIn(BaseModel):
    username: str
    password: str


class OrganisationChoice(BaseModel):
    tenant_id: str
    tenant_name: str
    profile: str
    user_name: str
    role: str


class LoginOut(BaseModel):
    access_token: str | None = None  # one organisation: signed in already
    token_type: str = "Bearer"  # noqa: S105  # the OAuth token type, not a secret
    expires_in: int = TOKEN_TTL_S
    ticket: str | None = None  # several: trade it at /auth/organisation within TICKET_TTL_S
    organisations: list[OrganisationChoice] = []


class ChooseIn(BaseModel):
    ticket: str
    tenant_id: str


password_router = APIRouter(prefix="/auth", tags=["dev"], include_in_schema=False)


async def _allowed(request: Request, db: AsyncDatabase[dict[str, Any]]) -> list[tuple[IdentityLink, User, Tenant]]:
    """The users LOGIN_AS names, in its order (one row per email that is an active user who can sign in here)."""
    idp = _idp(request)
    rows = {user.email.lower(): (link, user, tenant) for link, user, tenant in await _users(db, idp.issuer)}
    wanted = request.app.state.settings.login_as_emails
    return [rows[email] for email in wanted if email in rows]


@password_router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, db: Db) -> LoginOut:
    settings = request.app.state.settings
    expected = settings.login_password_hash.get_secret_value() if settings.login_password_hash else ""
    # Both are always checked, so a wrong username takes as long as a wrong password and says the same.
    name_ok = hmac.compare_digest(body.username.encode(), (settings.login_username or "").encode())
    password_ok = verify_password(body.password, expected)
    if not (name_ok and password_ok):
        log.warning("password sign-in refused", extra={"username_matched": name_ok})
        raise UnauthorizedError("The username or password is wrong.")
    idp = _idp(request)
    allowed = await _allowed(request, db)
    if not allowed:
        raise NotFoundError("LOGIN_AS is not a Sabha user who can sign in here; run scripts/admin/dev_seed.py.")
    if len(allowed) == 1:
        link, user, _ = allowed[0]
        log.info("password sign-in", extra={"user_id": user.id, "tenant_id": user.tenant_id})
        return LoginOut(access_token=idp.token(link.subject or "", user.email))
    return LoginOut(
        ticket=idp.ticket(settings.login_username, TICKET_TTL_S),
        organisations=[
            OrganisationChoice(tenant_id=tenant.id, tenant_name=tenant.name, profile=tenant.profile,
                               user_name=user.name, role=user.role)
            for _, user, tenant in allowed
        ],
    )  # fmt: skip


@password_router.post("/organisation", response_model=TokenOut)
async def choose_organisation(body: ChooseIn, request: Request, db: Db) -> TokenOut:
    idp = _idp(request)
    if not idp.ticket_is_valid(body.ticket):
        raise UnauthorizedError("Your sign-in has expired. Please sign in again.")
    for link, user, tenant in await _allowed(request, db):
        if tenant.id == body.tenant_id:
            log.info("password sign-in", extra={"user_id": user.id, "tenant_id": tenant.id})
            return TokenOut(access_token=idp.token(link.subject or "", user.email))
    raise NotFoundError("That organisation is not one you can sign in to.")
