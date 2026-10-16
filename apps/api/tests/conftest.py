"""Shared fixtures for the API tests: settings built in code and fake dependencies (no real services needed).

`make_client(checks=..., resources=..., token_verifier=..., principals=..., **settings_overrides)` builds an app and
returns a started TestClient; `client` is the default one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager
from typing import Any, Protocol

import pytest
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
