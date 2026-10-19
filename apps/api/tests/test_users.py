"""Invites, first login, GET /v1/me and the idempotency store (plan task P1.5b). Real MongoDB, fake identity provider.

Decisions these tests pin down (2026-10-19):
- Owners may invite any role; admins only manager, reviewer and staff (403 `role_not_allowed` otherwise).
- A first login links the pending invite for the verified email. Pending invites from two tenants: 403
  `ambiguous_invite`, never a silent choice. An unverified email: 403 `email_not_verified`.
- Every create needs an Idempotency-Key (CLAUDE.md). A replay returns the original response with
  `Idempotent-Replayed: true`; the same key with a different body is 422 `idempotency_key_reused`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.auth import TokenVerifier
from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Role, Tenant, User
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS

pytestmark = pytest.mark.integration

ISSUER = "https://auth.example.com"  # BASE_SETTINGS in conftest.py
AUDIENCE = "https://api.example.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class FakeIdp:
    """Discovery, JWKS and userinfo for ISSUER. `emails` maps subject -> (email, email_verified)."""

    emails: dict[str, tuple[str, bool]] = field(default_factory=dict)
    userinfo_calls: int = 0

    async def fetch(self, url: str) -> Mapping[str, Any]:
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return {"issuer": f"{ISSUER}/", "jwks_uri": f"{ISSUER}/jwks", "userinfo_endpoint": f"{ISSUER}/userinfo"}
        if url == f"{ISSUER}/jwks":
            entry = jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
            return {"keys": [{**entry, "kid": "k1", "use": "sig", "alg": "RS256"}]}
        raise httpx.ConnectError(url)

    async def fetch_userinfo(self, url: str, token: str) -> Mapping[str, Any]:
        assert url == f"{ISSUER}/userinfo"
        self.userinfo_calls += 1
        sub = jwt.decode(token, options={"verify_signature": False})["sub"]
        email, verified = self.emails[sub]
        return {"sub": sub, "email": email, "email_verified": verified}

    def token(self, sub: str) -> str:
        now = int(time.time())
        claims = {
            "iss": f"{ISSUER}/",
            "aud": [AUDIENCE, f"{ISSUER}/userinfo"],
            "sub": sub,
            "iat": now,
            "exp": now + 600,
        }
        return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "k1"})


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: FakeIdp

    def get(self, path: str, sub: str | None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}"} if sub else {}
        return self.client.get(path, headers=headers)

    def invite(self, sub: str, body: dict[str, Any], key: str | None = "k-1") -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post("/v1/users/invites", json=body, headers=headers)


# Existing, linked users: subject -> (tenant, user id, role)
SEEDED = {
    "google|owner-a": ("tenant-a", "u-owner-a", Role.OWNER),
    "google|admin-a": ("tenant-a", "u-admin-a", Role.ADMIN),
    "google|staff-a": ("tenant-a", "u-staff-a", Role.STAFF),
    "google|owner-b": ("tenant-b", "u-owner-b", Role.OWNER),
}


def seed(db: Database[dict[str, Any]]) -> None:
    for tenant_id, name in (("tenant-a", "Green Valley School"), ("tenant-b", "Blue Hills School")):
        tenant = Tenant.from_profile("school", name=name, plan=Plan.PILOT, id=tenant_id)
        db.tenants.insert_one(tenant.model_dump(by_alias=True))
    for sub, (tenant_id, user_id, role) in SEEDED.items():
        email = f"{user_id}@example.com"
        user = User(id=user_id, tenant_id=tenant_id, email=email, name=user_id, role=role, status="active")
        link = IdentityLink(tenant_id=tenant_id, issuer=ISSUER, subject=sub, email=email, user_id=user_id)
        db.users.insert_one(user.model_dump(by_alias=True))
        db.identities.insert_one(link.model_dump(by_alias=True))
    db.units.insert_one({"_id": "unit-a", "tenant_id": "tenant-a", "name": "Primary", "parent_id": None})


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    """One database for the module, with every index created up front: creating 16 collections per test is slow."""
    name = f"users_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def api(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Api:
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    seed(db)
    idp = FakeIdp()
    verifier = TokenVerifier(ISSUER, AUDIENCE, fetch=idp.fetch, fetch_userinfo=idp.fetch_userinfo)
    client = make_client(
        resources=open_resources,
        token_verifier=verifier,
        mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=shared_db,
        redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key_id="test",
        s3_secret_access_key="test",  # pragma: allowlist secret  (fake test value)
    )
    return Api(client, db, idp)


def problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


TEACHER = {"email": "  Asha.Rao@Example.com ", "name": "Asha Rao", "role": "staff", "unit_ids": ["unit-a"]}


# --- Invites ---


def test_owner_invites_a_user(api: Api) -> None:
    response = api.invite("google|owner-a", TEACHER)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "user_id": body["user_id"],
        "email": "asha.rao@example.com",
        "name": "Asha Rao",
        "role": "staff",
        "unit_ids": ["unit-a"],
        "status": "invited",
    }
    user = api.db.users.find_one({"_id": body["user_id"]})
    assert user is not None and user["tenant_id"] == "tenant-a" and user["status"] == "invited"
    link = api.db.identities.find_one({"user_id": body["user_id"]})
    assert link is not None
    assert (link["tenant_id"], link["issuer"], link["email"], link["subject"]) == (
        "tenant-a",
        ISSUER,
        "asha.rao@example.com",
        None,
    )


@pytest.mark.parametrize(
    ("inviter", "role", "allowed"),
    [
        ("google|owner-a", "owner", True),
        ("google|owner-a", "admin", True),
        ("google|admin-a", "manager", True),
        ("google|admin-a", "reviewer", True),
        ("google|admin-a", "staff", True),
        ("google|admin-a", "admin", False),
        ("google|admin-a", "owner", False),
    ],
)
def test_who_may_invite_which_role(api: Api, inviter: str, role: str, allowed: bool) -> None:
    response = api.invite(inviter, {**TEACHER, "role": role, "unit_ids": []})
    if allowed:
        assert response.status_code == 201, response.text
    else:
        problem(response, 403, "role_not_allowed")
        assert api.db.users.count_documents({"email": "asha.rao@example.com"}) == 0


def test_staff_cannot_invite(api: Api) -> None:
    problem(api.invite("google|staff-a", TEACHER), 403, "forbidden")


def test_inviting_an_existing_users_email_is_a_conflict(api: Api) -> None:
    assert api.invite("google|owner-a", TEACHER, key="k-1").status_code == 201
    problem(api.invite("google|owner-a", {**TEACHER, "name": "Someone"}, key="k-2"), 409, "user_exists")


def test_the_same_email_may_be_invited_by_another_tenant(api: Api) -> None:
    assert api.invite("google|owner-a", TEACHER).status_code == 201
    assert api.invite("google|owner-b", {**TEACHER, "unit_ids": []}).status_code == 201


def test_units_must_belong_to_the_tenant(api: Api) -> None:
    problem(api.invite("google|owner-b", TEACHER), 422, "unknown_unit")  # unit-a is tenant A's


@pytest.mark.parametrize(
    "extra", [{"id": "chosen"}, {"_id": "chosen"}, {"tenant_id": "tenant-b"}, {"status": "active"}]
)
def test_clients_cannot_choose_ids_tenants_or_status(api: Api, extra: dict[str, Any]) -> None:
    # /tenant-check finding 2: ids are generated by the server.
    problem(api.invite("google|owner-a", {**TEACHER, **extra}), 422, "validation_error")


def test_invites_need_a_signed_in_user(api: Api) -> None:
    response = api.client.post("/v1/users/invites", json=TEACHER, headers={"Idempotency-Key": "k"})
    problem(response, 401, "unauthorized")


# --- Idempotency ---


def test_create_without_an_idempotency_key_is_refused(api: Api) -> None:
    problem(api.invite("google|owner-a", TEACHER, key=None), 400, "idempotency_key_required")


@pytest.mark.parametrize("key", ["", " ", "x" * 256, "tab\there"])
def test_malformed_idempotency_keys_are_refused(api: Api, key: str) -> None:
    problem(api.invite("google|owner-a", TEACHER, key=key), 400, "invalid_idempotency_key")


def test_a_replay_returns_the_original_response(api: Api) -> None:
    first = api.invite("google|owner-a", TEACHER, key="replay-1")
    second = api.invite("google|owner-a", TEACHER, key="replay-1")
    assert (second.status_code, second.json()) == (first.status_code, first.json())
    assert second.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in first.headers
    assert api.db.users.count_documents({"email": "asha.rao@example.com"}) == 1


def test_the_same_key_with_a_different_body_is_refused(api: Api) -> None:
    assert api.invite("google|owner-a", TEACHER, key="k-x").status_code == 201
    problem(api.invite("google|owner-a", {**TEACHER, "name": "Other"}, key="k-x"), 422, "idempotency_key_reused")


def test_idempotency_keys_are_per_tenant(api: Api) -> None:
    assert api.invite("google|owner-a", TEACHER, key="shared").status_code == 201
    other = api.invite("google|owner-b", {**TEACHER, "unit_ids": []}, key="shared")
    assert other.status_code == 201 and "idempotent-replayed" not in other.headers
    assert api.db.users.count_documents({"email": "asha.rao@example.com"}) == 2


def test_a_failed_request_does_not_burn_its_key(api: Api) -> None:
    problem(api.invite("google|owner-b", TEACHER, key="retry"), 422, "unknown_unit")
    assert api.invite("google|owner-b", {**TEACHER, "unit_ids": []}, key="retry").status_code == 201


def test_a_request_still_in_progress_is_a_conflict(api: Api) -> None:
    api.db.idempotency_keys.insert_one(
        {
            "_id": "busy",
            "tenant_id": "tenant-a",
            "route": "POST /v1/users/invites",
            "key": "busy-key",
            "request_hash": "anything",
            "status": "in_progress",
            "created_at": time.time(),
        }
    )
    problem(api.invite("google|owner-a", TEACHER, key="busy-key"), 409, "request_in_progress")


# --- First login ---


def invite_and_get_id(api: Api, inviter: str = "google|owner-a", **changes: Any) -> str:
    response = api.invite(inviter, {**TEACHER, **changes}, key=str(uuid.uuid4()))
    assert response.status_code == 201, response.text
    user_id: str = response.json()["user_id"]
    return user_id


def test_first_login_links_the_invite_and_activates_the_user(api: Api) -> None:
    user_id = invite_and_get_id(api)
    api.idp.emails["google|asha"] = ("Asha.Rao@example.com", True)
    me = api.get("/v1/me", "google|asha")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["id"] == user_id and me.json()["user"]["role"] == "staff"
    link = api.db.identities.find_one({"user_id": user_id})
    user = api.db.users.find_one({"_id": user_id})
    assert link is not None and link["subject"] == "google|asha"
    assert user is not None and user["status"] == "active"

    calls = api.idp.userinfo_calls
    assert api.get("/v1/me", "google|asha").status_code == 200
    assert api.idp.userinfo_calls == calls  # later logins use the linked subject


def test_unverified_email_is_refused(api: Api) -> None:
    invite_and_get_id(api)
    api.idp.emails["google|asha"] = ("asha.rao@example.com", False)
    problem(api.get("/v1/me", "google|asha"), 403, "email_not_verified")
    assert api.db.identities.count_documents({"subject": "google|asha"}) == 0


def test_uninvited_login_is_refused(api: Api) -> None:
    api.idp.emails["google|mallory"] = ("mallory@example.com", True)
    problem(api.get("/v1/me", "google|mallory"), 403, "not_invited")


def test_invites_from_two_tenants_are_ambiguous(api: Api) -> None:
    invite_and_get_id(api, "google|owner-a")
    invite_and_get_id(api, "google|owner-b", unit_ids=[])
    api.idp.emails["google|asha"] = ("asha.rao@example.com", True)
    problem(api.get("/v1/me", "google|asha"), 403, "ambiguous_invite")
    assert api.db.identities.count_documents({"subject": "google|asha"}) == 0


def test_disabled_users_are_refused(api: Api) -> None:
    api.db.users.update_one({"_id": "u-staff-a"}, {"$set": {"status": "disabled"}})
    problem(api.get("/v1/me", "google|staff-a"), 403, "user_disabled")


# --- GET /v1/me ---


def test_me_returns_the_user_role_and_tenant_labels(api: Api) -> None:
    response = api.get("/v1/me", "google|admin-a")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"] == {
        "id": "u-admin-a",
        "email": "u-admin-a@example.com",
        "name": "u-admin-a",
        "role": "admin",
        "unit_ids": [],
    }
    tenant = body["tenant"]
    assert (tenant["id"], tenant["name"], tenant["profile"]) == ("tenant-a", "Green Valley School", "school")
    assert {"person", "recording", "unit"} <= set(tenant["labels"])
    assert "teaching" in tenant["enabled_types"]


def test_me_shows_only_the_callers_tenant(api: Api) -> None:
    assert api.get("/v1/me", "google|owner-b").json()["tenant"]["id"] == "tenant-b"


def test_me_needs_a_signed_in_user(api: Api) -> None:
    problem(api.get("/v1/me", None), 401, "unauthorized")
