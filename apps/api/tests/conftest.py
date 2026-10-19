"""Shared fixtures for the API tests: settings built in code and fake dependencies (no real services needed).

`make_client(checks=..., resources=..., token_verifier=..., principals=..., **settings_overrides)` builds an app and
returns a started TestClient; `client` is the default one.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from sabha_api.auth import PrincipalStore, TokenVerifier
from sabha_api.main import ResourcesFactory, create_app
from sabha_api.resources import Check, Resources
from sabha_core.settings import Settings

BASE_SETTINGS: dict[str, Any] = {
    "app_env": "test",
    "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
    "redis_url": "redis://localhost:6380/0",
    "s3_bucket_audio": "sabha-audio",
    "s3_bucket_artefacts": "sabha-artefacts",
    "s3_bucket_backups": "sabha-backups",
    "s3_endpoint_url": "http://localhost:9000",
    "oidc_issuer": "https://auth.example.com",
    "oidc_audience": "https://api.example.com",
    "oidc_client_id": "web",
    "cors_origins": ["http://localhost:5173"],
    "git_sha": "0123abc",
}


async def ok() -> object:
    return None


def fake_resources(checks: dict[str, Check] | None) -> ResourcesFactory:
    @asynccontextmanager
    async def factory(_: Settings) -> AsyncIterator[Resources]:
        yield Resources(readiness=checks or {"mongo": ok, "redis": ok, "storage": ok})

    return factory


class MakeClient(Protocol):
    def __call__(
        self,
        *,
        checks: dict[str, Check] | None = None,
        resources: ResourcesFactory | None = None,
        token_verifier: TokenVerifier | None = None,
        principals: PrincipalStore | None = None,
        **overrides: Any,
    ) -> TestClient: ...


@pytest.fixture
def make_client() -> Iterator[MakeClient]:
    with ExitStack() as stack:

        def make(
            *,
            checks: dict[str, Check] | None = None,
            resources: ResourcesFactory | None = None,
            token_verifier: TokenVerifier | None = None,
            principals: PrincipalStore | None = None,
            **overrides: Any,
        ) -> TestClient:
            settings = Settings(_env_file=None, **{**BASE_SETTINGS, **overrides})  # type: ignore[call-arg]
            app = create_app(
                settings,
                resources=resources or fake_resources(checks),
                token_verifier=token_verifier,
                principals=principals,
            )
            # raise_server_exceptions=False: we test what a real client receives, not the exception itself.
            return stack.enter_context(TestClient(app, raise_server_exceptions=False))

        yield make


@pytest.fixture
def client(make_client: MakeClient) -> TestClient:
    return make_client()


# --- A fake identity provider for tests that sign in (test_users.py, test_recordings.py) ---

OIDC_ISSUER = BASE_SETTINGS["oidc_issuer"]
OIDC_AUDIENCE = BASE_SETTINGS["oidc_audience"]
_IDP_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class FakeIdp:
    """Discovery, JWKS and userinfo for the test issuer. `emails` maps subject -> (email, email_verified)."""

    emails: dict[str, tuple[str, bool]] = field(default_factory=dict)
    userinfo_calls: int = 0

    async def fetch(self, url: str) -> Mapping[str, Any]:
        if url == f"{OIDC_ISSUER}/.well-known/openid-configuration":
            return {
                "issuer": f"{OIDC_ISSUER}/",
                "jwks_uri": f"{OIDC_ISSUER}/jwks",
                "userinfo_endpoint": f"{OIDC_ISSUER}/userinfo",
            }
        if url == f"{OIDC_ISSUER}/jwks":
            entry = jwt.algorithms.RSAAlgorithm.to_jwk(_IDP_KEY.public_key(), as_dict=True)
            return {"keys": [{**entry, "kid": "k1", "use": "sig", "alg": "RS256"}]}
        raise httpx.ConnectError(url)

    async def fetch_userinfo(self, url: str, token: str) -> Mapping[str, Any]:
        assert url == f"{OIDC_ISSUER}/userinfo"
        self.userinfo_calls += 1
        sub = jwt.decode(token, options={"verify_signature": False})["sub"]
        email, verified = self.emails[sub]
        return {"sub": sub, "email": email, "email_verified": verified}

    def token(self, sub: str) -> str:
        now = int(time.time())
        claims = {
            "iss": f"{OIDC_ISSUER}/",
            "aud": [OIDC_AUDIENCE, f"{OIDC_ISSUER}/userinfo"],
            "sub": sub,
            "iat": now,
            "exp": now + 600,
        }
        return jwt.encode(claims, _IDP_KEY, algorithm="RS256", headers={"kid": "k1"})

    def verifier(self) -> TokenVerifier:
        return TokenVerifier(OIDC_ISSUER, OIDC_AUDIENCE, fetch=self.fetch, fetch_userinfo=self.fetch_userinfo)


@pytest.fixture
def fake_idp() -> FakeIdp:
    return FakeIdp()
