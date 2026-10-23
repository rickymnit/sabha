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
from sabha_api.deps import _database
from sabha_api.errors import NotFoundError
from sabha_core.models import IdentityLink, Tenant, User
from sabha_core.repo import SystemRepo, TenantRepo

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
