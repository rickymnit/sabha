"""The audit log (P1.8): append-only, readable by owners and admins through GET /v1/audit.

- Entries are newest first, each with who did it (name and role), the action, its target (with the recording's
  title or the person's name where there is one) and its details. Filters: action, actor, target and a time range;
  cursor pagination.
- Owners and admins only; everyone else gets 403. A tenant never sees another tenant's entries.
- Inviting someone writes user.invite (the invited user as target, their role in the details, never the email).
- Entries cannot be changed or deleted: the repository refuses (packages/core/tests/test_repo.py).

The permission matrix (tests/security) covers the route for every caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import AuditEntry, IdentityLink, Person, Recording, Role, Tenant, Unit, User, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, name, role)
    "owner": (T, "u-owner", "Priya Sharma", Role.OWNER),
    "admin": (T, "u-admin", "Neha Joshi", Role.ADMIN),
    "manager": (T, "u-manager", "Meena Iyer", Role.MANAGER),
    "reviewer": (T, "u-reviewer", "Rahul Verma", Role.REVIEWER),
    "asha": (T, "u-asha", "Asha Rao", Role.STAFF),
    "owner-b": (B, "u-owner-b", "Kabir Mehta", Role.OWNER),
}


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any

    def get(self, sub: str, path: str = "/v1/audit") -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})

    def items(self, sub: str = "owner", query: str = "") -> list[dict[str, Any]]:
        response = self.get(sub, f"/v1/audit{query}")
        assert response.status_code == 200, response.text
        items: list[dict[str, Any]] = response.json()["items"]
        return items


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"audit_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


def insert(db: Database[dict[str, Any]], collection: str, doc: Any) -> None:
    db[collection].insert_one(doc.model_dump(by_alias=True))


@pytest.fixture
def api(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str,
        fake_idp: Any, s3_storage: Any) -> Api:  # fmt: skip
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    client = make_client(
        resources=open_resources, token_verifier=fake_idp.verifier(), mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=shared_db, redis_url="redis://127.0.0.1:1/0", s3_endpoint_url=s3_storage.endpoint_url,
        s3_access_key_id=s3_storage.access_key_id, s3_secret_access_key=s3_storage.secret_access_key,
    )  # fmt: skip
    issuer = client.app.state.settings.oidc_issuer
    insert(db, "tenants", Tenant.from_profile("school", name="Sunrise", plan=Plan.PILOT, id=T))
    insert(db, "tenants", Tenant.from_profile("company", name="Brightpath", plan=Plan.PILOT, id=B))
    insert(db, "units", Unit(id="unit-1", tenant_id=T, name="Class 1"))
    for sub, (tenant, user_id, name, role) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant, email=f"{sub}@example.com", name=name, role=role,
                                 unit_ids=["unit-1"] if role in (Role.MANAGER, Role.REVIEWER, Role.STAFF) else [],
                                 status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha Rao", unit_id="unit-1", user_id="u-asha"))
    insert(db, "recordings", Recording(id="r-1", tenant_id=T, type=ConversationType.TEACHING,
                                       status=RecordingStatus.COMPLETED, consent_ref="c", person_id="p-asha",
                                       unit_id="unit-1", file_name="Fractions, Class 7B.mp3"))  # fmt: skip
    return Api(client, db, fake_idp)


def entry(api: Api, *, tenant: str = T, actor: str = "u-owner", role: str = "owner", action: str = "recording.play",
          target_type: str = "recording", target_id: str = "r-1", minutes_ago: int = 0,
          meta: dict[str, Any] | None = None) -> None:  # fmt: skip
    insert(api.db, "audit_log", AuditEntry(tenant_id=tenant, actor_user_id=actor, actor_role=role, action=action,
                                           target_type=target_type, target_id=target_id, meta=meta or {},
                                           at=utc_now() - timedelta(minutes=minutes_ago)))  # fmt: skip


# --- Reading ---


@pytest.mark.parametrize("sub", ["owner", "admin"])
def test_owners_and_admins_read_the_log_newest_first(api: Api, sub: str) -> None:
    entry(api, minutes_ago=10)
    entry(api, actor="u-admin", role="admin", action="settings.update", target_type="tenant", target_id=T,
          meta={"before": {"labels": {"person": "Teacher"}}, "after": {"labels": {"person": "Educator"}}})  # fmt: skip
    newest, older = api.items(sub)
    assert newest["action"] == "settings.update"
    assert newest["actor"] == {"id": "u-admin", "name": "Neha Joshi", "role": "admin"}
    assert newest["target"] == {"type": "tenant", "id": T, "label": None}
    assert newest["meta"]["after"] == {"labels": {"person": "Educator"}}
    assert older["action"] == "recording.play"
    assert older["target"] == {"type": "recording", "id": "r-1", "label": "Fractions, Class 7B"}
    assert older["actor"]["name"] == "Priya Sharma"
    assert newest["at"] > older["at"]


@pytest.mark.parametrize("sub", ["manager", "reviewer", "asha"])
def test_everyone_else_is_refused(api: Api, sub: str) -> None:
    entry(api)
    response = api.get(sub)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_a_tenant_sees_only_its_own_entries(api: Api) -> None:
    entry(api)
    entry(api, tenant=B, actor="u-owner-b", target_id="r-b")
    assert [e["target"]["id"] for e in api.items("owner")] == ["r-1"]
    assert [e["target"]["id"] for e in api.items("owner-b")] == ["r-b"]


def test_an_entry_by_someone_since_removed_still_shows(api: Api) -> None:
    entry(api, actor="u-gone")
    [item] = api.items()
    assert item["actor"] == {"id": "u-gone", "name": None, "role": "owner"}


# --- Filters and pages ---


def test_filters(api: Api) -> None:
    entry(api, minutes_ago=90)
    entry(api, actor="u-admin", role="admin", minutes_ago=30)
    entry(api, action="analysis.view", minutes_ago=5)
    entry(api, action="recording.play", target_id="r-2", minutes_ago=1)
    assert len(api.items(query="?action=recording.play")) == 3
    assert [e["actor"]["id"] for e in api.items(query="?actor_user_id=u-admin")] == ["u-admin"]
    assert len(api.items(query="?target_id=r-1")) == 3
    since = (utc_now() - timedelta(minutes=60)).isoformat().replace("+00:00", "Z")
    until = (utc_now() - timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
    assert len(api.items(query=f"?from={since}&to={until}")) == 2


def test_pages_with_a_cursor(api: Api) -> None:
    for minutes in range(5):
        entry(api, minutes_ago=minutes)
    first = api.get("owner", "/v1/audit?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = api.get("owner", f"/v1/audit?limit=2&cursor={first['next_cursor']}").json()
    third = api.get("owner", f"/v1/audit?limit=2&cursor={second['next_cursor']}").json()
    ids = [e["id"] for page in (first, second, third) for e in page["items"]]
    assert len(ids) == len(set(ids)) == 5
    assert third["next_cursor"] is None


@pytest.mark.parametrize("query", ["?limit=0", "?limit=201", "?cursor=not-a-cursor", "?from=yesterday"])
def test_bad_queries_are_refused(api: Api, query: str) -> None:
    assert api.get("owner", f"/v1/audit{query}").status_code in (400, 422)


# --- What writes entries ---


def test_an_invite_is_audited_without_the_email(api: Api) -> None:
    headers = {"Authorization": f"Bearer {api.idp.token('owner')}", "Idempotency-Key": uuid.uuid4().hex}
    body = {"email": "new.teacher@example.com", "name": "New Teacher", "role": "staff", "unit_ids": ["unit-1"]}
    created = api.client.post("/v1/users/invites", json=body, headers=headers)
    assert created.status_code == 201, created.text
    [item] = api.items(query="?action=user.invite")
    assert item["actor"]["id"] == "u-owner"
    assert item["target"] == {"type": "user", "id": created.json()["user_id"], "label": "New Teacher"}
    assert item["meta"] == {"role": "staff", "unit_ids": ["unit-1"]}
    assert "new.teacher@example.com" not in str(api.db["audit_log"].find_one({"action": "user.invite"}))
