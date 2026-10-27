"""Workspace settings (P1.7): an owner or admin renames the product's words and switches conversation types.

- GET /v1/settings and PATCH /v1/settings, owners and admins only (the design: "Admins can rename any of these in
  Settings", docs/design/source/Setup.dc.html). Everyone else gets 403; /v1/me already gives them the labels.
- Labels: any of the six words, each 1 to 40 characters after trimming; unknown keys are refused.
- Conversation types: at least one; only types with a rubric for the tenant's profile; at most the plan's number
  (Starter any two, pilot and Growth all five: docs/design/source/Plans.dc.html, Setup.dc.html).
- A type switched off refuses new uploads; recordings already made stay readable.
- Every change writes one audit entry with the fields before and after; a request that changes nothing writes none.
- A tenant's settings never change another tenant (golden rule 1).

The permission matrix (tests/security) covers both routes for every caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Person, Recording, Role, Tenant, Unit, User
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, role, units)
    "owner": (T, "u-owner", Role.OWNER, []),
    "admin": (T, "u-admin", Role.ADMIN, []),
    "manager": (T, "u-manager", Role.MANAGER, ["unit-1"]),
    "reviewer": (T, "u-reviewer", Role.REVIEWER, ["unit-1"]),
    "asha": (T, "u-asha", Role.STAFF, ["unit-1"]),
    "owner-b": (B, "u-owner-b", Role.OWNER, []),
}


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any

    def auth(self, sub: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.idp.token(sub)}"}

    def get(self, sub: str, path: str = "/v1/settings") -> httpx.Response:
        return self.client.get(path, headers=self.auth(sub))

    def patch(self, sub: str, body: dict[str, Any]) -> httpx.Response:
        return self.client.patch("/v1/settings", json=body, headers=self.auth(sub))

    def tenant(self, tenant_id: str = T) -> dict[str, Any]:
        found = self.db["tenants"].find_one({"_id": tenant_id})
        assert found is not None
        return found

    def audits(self) -> list[dict[str, Any]]:
        return list(self.db["audit_log"].find({"tenant_id": T, "action": "settings.update"}))


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"settings_{uuid.uuid4().hex[:12]}"
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
    for sub, (tenant, user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    return Api(client, db, fake_idp)


def problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- Reading ---


@pytest.mark.parametrize("sub", ["owner", "admin"])
def test_owners_and_admins_read_the_settings(api: Api, sub: str) -> None:
    response = api.get(sub)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["name"] == "Sunrise"
    assert out["profile"] == "school"
    assert out["plan"] == "pilot"
    assert out["labels"]["person"] == "Teacher"
    assert out["labels"]["recording_plural"] == "Lessons"
    assert out["enabled_types"] == ["teaching", "reception"]
    assert out["max_types"] == 5
    # Every type in the setup screen's order, whether it is on and whether it can be switched on (has a rubric).
    assert out["types"] == [
        {"type": "teaching", "enabled": True, "available": True},
        {"type": "counselling", "enabled": False, "available": False},
        {"type": "reception", "enabled": True, "available": True},
        {"type": "meeting", "enabled": False, "available": False},
        {"type": "sales", "enabled": False, "available": False},
    ]


@pytest.mark.parametrize("sub", ["manager", "reviewer", "asha"])
def test_others_may_neither_read_nor_change_the_settings(api: Api, sub: str) -> None:
    problem(api.get(sub), 403, "forbidden")
    problem(api.patch(sub, {"labels": {"person": "Educator"}}), 403, "forbidden")
    assert api.tenant()["labels"]["person"] == "Teacher"


def test_signed_out_callers_get_401(api: Api) -> None:
    assert api.client.get("/v1/settings").status_code == 401
    assert api.client.patch("/v1/settings", json={"name": "x"}).status_code == 401


# --- Labels and name ---


@pytest.mark.parametrize("sub", ["owner", "admin"])
def test_renaming_words_changes_them_everywhere(api: Api, sub: str) -> None:
    response = api.patch(sub, {"labels": {"person": "  Educator ", "person_plural": "Educators"}})
    assert response.status_code == 200, response.text
    assert response.json()["labels"]["person"] == "Educator"
    labels = api.get("asha", "/v1/me").json()["tenant"]["labels"]
    assert labels["person"] == "Educator" and labels["person_plural"] == "Educators"
    assert labels["recording"] == "Lesson"  # words not sent are kept


def test_renaming_the_organisation(api: Api) -> None:
    assert api.patch("owner", {"name": "  Sunrise Public School  "}).status_code == 200
    assert api.get("manager", "/v1/me").json()["tenant"]["name"] == "Sunrise Public School"


@pytest.mark.parametrize(
    "body",
    [
        {"labels": {"person": ""}},
        {"labels": {"person": "   "}},
        {"labels": {"person": "x" * 41}},
        {"labels": {"student": "Pupil"}},  # unknown word
        {"labels": {"person": None}},
        {"name": ""},
        {"name": "x" * 121},
        {"plan": "growth"},  # not a setting: plans change through Sabha
        {"profile": "company"},
        {"enabled_types": []},
        {"enabled_types": ["teaching", "teaching"]},
        {"enabled_types": ["cooking"]},
    ],
)
def test_bad_values_are_refused(api: Api, body: dict[str, Any]) -> None:
    problem(api.patch("owner", body), 422, "validation_error")
    tenant = api.tenant()
    assert tenant["name"] == "Sunrise" and tenant["labels"]["person"] == "Teacher" and tenant["plan"] == "pilot"
    assert api.audits() == []


# --- Conversation types ---


def test_switching_types_on_and_off(api: Api) -> None:
    response = api.patch("owner", {"enabled_types": ["reception", "teaching"]})
    assert response.status_code == 200, response.text
    assert response.json()["enabled_types"] == ["teaching", "reception"]  # stored in the setup screen's order
    response = api.patch("owner", {"enabled_types": ["reception"]})
    assert response.json()["enabled_types"] == ["reception"]
    assert api.get("asha", "/v1/me").json()["tenant"]["enabled_types"] == ["reception"]


def test_a_type_without_a_rubric_cannot_be_switched_on(api: Api) -> None:
    response = api.patch("owner", {"enabled_types": ["teaching", "meeting"]})
    problem(response, 422, "type_unavailable")
    assert "meeting" in response.json()["detail"].lower()
    assert api.tenant()["enabled_types"] == ["teaching", "reception"]


def test_a_type_already_on_without_a_rubric_does_not_block_other_changes(api: Api) -> None:
    api.db["tenants"].update_one({"_id": T}, {"$set": {"enabled_types": ["teaching", "counselling", "reception"]}})
    response = api.patch("owner", {"enabled_types": ["teaching", "counselling"]})
    assert response.status_code == 200, response.text
    assert response.json()["enabled_types"] == ["teaching", "counselling"]


def test_the_plan_limits_how_many_types_are_on(api: Api) -> None:
    api.db["tenants"].update_one({"_id": B}, {"$set": {"plan": "starter", "enabled_types": ["reception", "sales"]}})
    assert api.get("owner-b").json()["max_types"] == 2
    response = api.patch("owner-b", {"enabled_types": ["reception", "meeting", "sales"]})
    problem(response, 422, "plan_limit")
    assert "2" in response.json()["detail"]
    assert api.tenant(B)["enabled_types"] == ["reception", "sales"]
    assert api.patch("owner-b", {"enabled_types": ["sales", "meeting"]}).status_code == 200


def test_a_tenant_over_its_limit_can_still_save_an_unchanged_list(api: Api) -> None:
    # Sabha may set a tenant up with more types than its plan (a trial); resending them is not a change.
    api.db["tenants"].update_one({"_id": B}, {"$set": {"plan": "starter"}})
    response = api.patch("owner-b", {"name": "Brightpath Software", "enabled_types": ["reception", "meeting", "sales"]})
    assert response.status_code == 200, response.text
    assert response.json()["enabled_types"] == ["reception", "meeting", "sales"]


def test_a_type_switched_off_refuses_uploads_but_keeps_old_recordings(api: Api) -> None:
    insert(api.db, "recordings", Recording(id="r-old", tenant_id=T, type=ConversationType.RECEPTION,
                                           status=RecordingStatus.COMPLETED, consent_ref="c", person_id="p-asha",
                                           unit_id="unit-1", file_name="call.mp3"))  # fmt: skip
    assert api.patch("owner", {"enabled_types": ["teaching"]}).status_code == 200
    upload = {"type": "reception", "file_name": "call.mp3", "size_bytes": 1024, "content_type": "audio/mpeg",
              "person_id": "p-asha", "consent_ref": "c"}  # fmt: skip
    created = api.client.post("/v1/recordings", json=upload,
                               headers={**api.auth("owner"), "Idempotency-Key": uuid.uuid4().hex})  # fmt: skip
    problem(created, 422, "type_not_enabled")
    assert api.get("owner", "/v1/recordings/r-old").status_code == 200


# --- Audit and isolation ---


def test_every_change_is_audited_with_before_and_after(api: Api) -> None:
    api.patch("admin", {"labels": {"person": "Educator", "recording": "Lesson"}, "enabled_types": ["teaching"]})
    [entry] = api.audits()
    assert entry["actor_user_id"] == "u-admin"
    assert entry["target_type"] == "tenant" and entry["target_id"] == T
    # Only what changed: "recording" was sent with its current value.
    assert entry["meta"] == {
        "before": {"labels": {"person": "Teacher"}, "enabled_types": ["teaching", "reception"]},
        "after": {"labels": {"person": "Educator"}, "enabled_types": ["teaching"]},
    }


def test_a_request_that_changes_nothing_writes_no_audit(api: Api) -> None:
    response = api.patch("owner", {"name": "Sunrise", "labels": {"person": "Teacher"}})
    assert response.status_code == 200
    assert api.audits() == []


def test_settings_never_reach_another_tenant(api: Api) -> None:
    assert api.patch("owner-b", {"name": "Brightpath Software", "labels": {"person": "Agent"}}).status_code == 200
    mine, theirs = api.get("owner").json(), api.get("owner-b").json()
    assert mine["name"] == "Sunrise" and mine["labels"]["person"] == "Teacher"
    assert theirs["name"] == "Brightpath Software" and theirs["labels"]["person"] == "Agent"
    assert list(api.db["audit_log"].find({"tenant_id": T})) == []
