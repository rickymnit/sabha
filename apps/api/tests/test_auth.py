"""Authentication and roles (P1.5): token validation, signing-key rotation, invites and role checks.

Tokens are signed with RSA keys generated here and served from a fake discovery document and JWKS, so no identity
provider is needed. Two routes are added to the app for the tests: one for any signed-in user, one for owners and
admins only.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from sabha_api.auth import Identity, Principal, Role, TokenVerifier, current_principal, require_role
from sabha_api.auth.oidc import JWKS_MIN_REFETCH_S, JWKS_TTL_S, LEEWAY_S

ISSUER = "https://sabha-dev.example.auth0.com"  # Auth0 issuers end in "/"; settings store it without
AUDIENCE = "https://api.example.com"
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY_1, KEY_2, STRANGER = new_key(), new_key(), new_key()


def jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    entry: dict[str, Any] = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**entry, "kid": kid, "use": "sig", "alg": "RS256"}


@dataclass
class FakeProvider:
    """Serves the discovery document and JWKS; `down` makes every fetch fail; `fetches` counts JWKS fetches."""

    keys: list[dict[str, Any]] = field(default_factory=lambda: [jwk(KEY_1, "k1")])
    issuer: str = ISSUER + "/"
    down: bool = False
    fetches: int = 0

    async def fetch(self, url: str) -> Mapping[str, Any]:
        if self.down:
            raise httpx.ConnectError("provider down")
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return {"issuer": self.issuer, "jwks_uri": JWKS_URI}
        if url == JWKS_URI:
            self.fetches += 1
            return {"keys": self.keys}
        raise httpx.HTTPStatusError("not found", request=httpx.Request("GET", url), response=httpx.Response(404))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def token(
    *,
    key: rsa.RSAPrivateKey = KEY_1,
    kid: str | None = "k1",
    sub: str | None = "google-oauth2|alice",
    iss: str = ISSUER + "/",
    aud: str | list[str] = AUDIENCE,
    expires_in: float = 3600,
    **claims: Any,
) -> str:
    now = int(time.time())
    body: dict[str, Any] = {"iss": iss, "aud": aud, "iat": now, "exp": now + expires_in, **claims}
    if sub is not None:
        body["sub"] = sub
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid} if kid else None)


ALICE = Principal(user_id="u-alice", tenant_id="t-1", role=Role.STAFF, unit_ids=("unit-a",))
BOB = Principal(user_id="u-bob", tenant_id="t-1", role=Role.ADMIN, unit_ids=())


class InMemoryPrincipals:
    def __init__(self, by_subject: Mapping[str, Principal]) -> None:
        self.by_subject = by_subject

    async def principal_for(self, identity: Identity, access_token: str) -> Principal | None:
        assert identity.issuer == ISSUER
        return self.by_subject.get(identity.subject)


PRINCIPALS = InMemoryPrincipals({"google-oauth2|alice": ALICE, "google-oauth2|bob": BOB})


BuildClient = Callable[..., TestClient]


@pytest.fixture
def build_client(make_client: Callable[..., TestClient]) -> BuildClient:
    """A started client whose verifier reads keys from `provider`, plus two test routes."""

    def build(
        provider: FakeProvider, *, principals: InMemoryPrincipals | None = PRINCIPALS, clock: Clock | None = None
    ) -> TestClient:
        verifier = TokenVerifier(ISSUER + "/", AUDIENCE, fetch=provider.fetch, clock=clock or Clock())
        test_client = make_client(token_verifier=verifier, principals=principals)
        app = test_client.app
        assert isinstance(app, FastAPI)

        @app.get("/v1/test/whoami")
        async def whoami(principal: Annotated[Principal, Depends(current_principal)]) -> dict[str, Any]:
            return {"user_id": principal.user_id, "tenant_id": principal.tenant_id, "role": principal.role}

        @app.get("/v1/test/admin-only")
        async def admin_only(
            principal: Annotated[Principal, Depends(require_role(Role.OWNER, Role.ADMIN))],
        ) -> dict[str, str]:
            return {"user_id": principal.user_id}

        return test_client

    return build


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(build_client: BuildClient, provider: FakeProvider) -> TestClient:
    return build_client(provider)


def get(client: TestClient, path: str, bearer: str | None) -> httpx.Response:
    return client.get(path, headers={"Authorization": f"Bearer {bearer}"} if bearer is not None else {})


def assert_problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


# --- Valid tokens ---


def test_valid_token_returns_the_principal(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", token())
    assert response.status_code == 200
    assert response.json() == {"user_id": "u-alice", "tenant_id": "t-1", "role": "staff"}


def test_issuer_without_trailing_slash_is_accepted(client: TestClient) -> None:
    assert get(client, "/v1/test/whoami", token(iss=ISSUER)).status_code == 200


def test_audience_list_containing_ours_is_accepted(client: TestClient) -> None:
    # Auth0 adds its /userinfo audience when the openid scope is requested.
    assert get(client, "/v1/test/whoami", token(aud=[AUDIENCE, f"{ISSUER}/userinfo"])).status_code == 200


def test_recently_expired_token_within_leeway_is_accepted(client: TestClient) -> None:
    assert get(client, "/v1/test/whoami", token(expires_in=-(LEEWAY_S - 10))).status_code == 200


# --- 401: no token or an invalid one ---


def test_missing_token_is_401_with_a_bearer_challenge(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", None)
    assert_problem(response, 401, "unauthorized")
    assert response.headers["www-authenticate"] == "Bearer"


def test_non_bearer_scheme_is_401(client: TestClient) -> None:
    response = client.get("/v1/test/whoami", headers={"Authorization": "Basic YWxpY2U6cGFzcw=="})
    assert_problem(response, 401, "unauthorized")


def test_expired_token_is_401(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", token(expires_in=-(LEEWAY_S + 60)))
    assert_problem(response, 401, "unauthorized")
    assert response.json()["detail"] == "The access token has expired."
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


def test_wrong_audience_is_401(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", token(aud="https://other-api.example.com"))
    assert_problem(response, 401, "unauthorized")
    assert response.json()["detail"] == "The access token is not for this API."


def test_wrong_issuer_is_401(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", token(iss="https://evil.example.com/"))
    assert_problem(response, 401, "unauthorized")


@pytest.mark.parametrize("claim", ["exp", "sub", "aud", "iss"])
def test_token_missing_a_required_claim_is_401(client: TestClient, claim: str) -> None:
    now = int(time.time())
    body = {"iss": ISSUER + "/", "aud": AUDIENCE, "sub": "google-oauth2|alice", "exp": now + 60}
    del body[claim]
    response = get(client, "/v1/test/whoami", jwt.encode(body, KEY_1, algorithm="RS256", headers={"kid": "k1"}))
    assert_problem(response, 401, "unauthorized")


def test_token_signed_by_another_key_with_a_known_kid_is_401(client: TestClient) -> None:
    assert_problem(get(client, "/v1/test/whoami", token(key=STRANGER)), 401, "unauthorized")


def test_hmac_token_signed_with_the_public_key_is_401(client: TestClient) -> None:
    # The classic algorithm-confusion attack: HS256 with the RSA public key as the shared secret.
    forged = jwt.encode(
        {"iss": ISSUER + "/", "aud": AUDIENCE, "sub": "google-oauth2|bob", "exp": int(time.time()) + 60},
        "attacker-chosen-secret-standing-in-for-the-public-key",
        algorithm="HS256",
        headers={"kid": "k1"},
    )
    response = get(client, "/v1/test/whoami", forged)
    assert_problem(response, 401, "unauthorized")
    assert response.json()["detail"] == "The access token uses an unsupported signing algorithm."


def test_unsigned_token_is_401(client: TestClient) -> None:
    def part(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    claims = {"iss": ISSUER + "/", "aud": AUDIENCE, "sub": "google-oauth2|bob", "exp": int(time.time()) + 60}
    unsigned = f"{part({'alg': 'none', 'typ': 'JWT', 'kid': 'k1'})}.{part(claims)}."
    response = get(client, "/v1/test/whoami", unsigned)
    assert_problem(response, 401, "unauthorized")
    assert response.json()["detail"] == "The access token uses an unsupported signing algorithm."


def test_token_without_kid_is_401(client: TestClient) -> None:
    assert_problem(get(client, "/v1/test/whoami", token(kid=None)), 401, "unauthorized")


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c"])
def test_malformed_token_is_401(client: TestClient, garbage: str) -> None:
    assert_problem(get(client, "/v1/test/whoami", garbage), 401, "unauthorized")


# --- 403: not invited, or the wrong role ---


def test_valid_token_for_an_uninvited_identity_is_403(client: TestClient) -> None:
    response = get(client, "/v1/test/whoami", token(sub="google-oauth2|mallory"))
    assert_problem(response, 403, "not_invited")


def test_staff_on_an_admin_route_is_403(client: TestClient) -> None:
    assert_problem(get(client, "/v1/test/admin-only", token()), 403, "forbidden")


def test_admin_on_an_admin_route_is_allowed(client: TestClient) -> None:
    response = get(client, "/v1/test/admin-only", token(sub="google-oauth2|bob"))
    assert response.status_code == 200
    assert response.json() == {"user_id": "u-bob"}


def test_role_check_runs_after_authentication(client: TestClient) -> None:
    assert_problem(get(client, "/v1/test/admin-only", None), 401, "unauthorized")


def test_require_role_needs_at_least_one_role() -> None:
    with pytest.raises(ValueError, match="at least one role"):
        require_role()


def test_without_a_principal_store_protected_routes_answer_503(
    build_client: BuildClient, provider: FakeProvider
) -> None:
    test_client = build_client(provider, principals=None)
    assert_problem(get(test_client, "/v1/test/whoami", token()), 503, "not_ready")


# --- Signing keys: caching, rotation, provider outages ---


def test_keys_are_fetched_once_and_cached(client: TestClient, provider: FakeProvider) -> None:
    for _ in range(3):
        assert get(client, "/v1/test/whoami", token()).status_code == 200
    assert provider.fetches == 1


def test_rotated_key_is_picked_up_by_a_refetch(build_client: BuildClient, provider: FakeProvider) -> None:
    clock = Clock()
    test_client = build_client(provider, clock=clock)
    assert get(test_client, "/v1/test/whoami", token()).status_code == 200
    provider.keys = [jwk(KEY_1, "k1"), jwk(KEY_2, "k2")]
    clock.now += JWKS_MIN_REFETCH_S
    assert get(test_client, "/v1/test/whoami", token(key=KEY_2, kid="k2")).status_code == 200
    assert provider.fetches == 2


def test_unknown_kids_cannot_make_us_hammer_the_provider(client: TestClient, provider: FakeProvider) -> None:
    assert get(client, "/v1/test/whoami", token()).status_code == 200
    for i in range(5):
        response = get(client, "/v1/test/whoami", token(key=STRANGER, kid=f"made-up-{i}"))
        assert_problem(response, 401, "unauthorized")
        assert response.json()["detail"] == "The access token was signed by an unknown key."
    assert provider.fetches == 1


def test_keys_are_refetched_after_the_ttl(build_client: BuildClient, provider: FakeProvider) -> None:
    clock = Clock()
    test_client = build_client(provider, clock=clock)
    get(test_client, "/v1/test/whoami", token())
    clock.now += JWKS_TTL_S
    assert get(test_client, "/v1/test/whoami", token()).status_code == 200
    assert provider.fetches == 2


def test_provider_down_with_cached_keys_keeps_working(build_client: BuildClient, provider: FakeProvider) -> None:
    clock = Clock()
    test_client = build_client(provider, clock=clock)
    get(test_client, "/v1/test/whoami", token())
    provider.down = True
    clock.now += JWKS_TTL_S
    assert get(test_client, "/v1/test/whoami", token()).status_code == 200


def test_provider_down_with_no_keys_is_503_not_401(build_client: BuildClient, provider: FakeProvider) -> None:
    provider.down = True
    test_client = build_client(provider)
    assert_problem(get(test_client, "/v1/test/whoami", token()), 503, "auth_unavailable")


def test_discovery_naming_another_issuer_is_refused(build_client: BuildClient, provider: FakeProvider) -> None:
    provider.issuer = "https://evil.example.com/"
    test_client = build_client(provider)
    assert_problem(get(test_client, "/v1/test/whoami", token()), 503, "auth_unavailable")


def test_jwks_without_usable_keys_is_refused(build_client: BuildClient, provider: FakeProvider) -> None:
    provider.keys = [{"kty": "oct", "kid": "k1", "k": "c2VjcmV0"}, {**jwk(KEY_1, "k1"), "use": "enc"}]
    test_client = build_client(provider)
    assert_problem(get(test_client, "/v1/test/whoami", token()), 503, "auth_unavailable")


def test_concurrent_requests_on_a_cold_cache_fetch_once(provider: FakeProvider) -> None:
    verifier = TokenVerifier(ISSUER, AUDIENCE, fetch=provider.fetch, clock=Clock())

    async def verify_many() -> list[Identity]:
        return await asyncio.gather(*(verifier.verify(token()) for _ in range(10)))

    identities = asyncio.run(verify_many())
    assert {i.subject for i in identities} == {"google-oauth2|alice"}
    assert provider.fetches == 1


def test_openapi_declares_the_bearer_scheme(client: TestClient) -> None:
    schemes = client.get("/openapi.json").json()["components"]["securitySchemes"]
    assert schemes["HTTPBearer"]["scheme"] == "bearer"
