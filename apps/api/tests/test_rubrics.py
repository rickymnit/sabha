"""Reading rubrics (P6.8, owner's decision 2026-10-27): everyone signed in, staff included, may read the rubrics of
their organisation's conversation types, so they can see how they are scored. Read-only: editing and publishing
need the calibration sample test (P5.9).

- GET /v1/rubrics: per enabled conversation type, the rubric in use (the profile's) and its other versions, newest
  first.
- GET /v1/rubrics/{rubric_id}: one rubric of that family: its dimensions (weight, quotes required, what it measures,
  the 1-5 scale with examples), its versions, and what changed from the version before.
- Rubrics of types the organisation has switched off, of another profile, or that do not exist answer 404.

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
from sabha_core.models import IdentityLink, Role, Tenant, User
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, role)
    "owner": (T, "u-owner", Role.OWNER),
    "manager": (T, "u-manager", Role.MANAGER),
    "asha": (T, "u-asha", Role.STAFF),
    "owner-b": (B, "u-owner-b", Role.OWNER),
}


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any

    def get(self, sub: str, path: str) -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"rubrics_{uuid.uuid4().hex[:12]}"
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
    for sub, (tenant, user_id, role) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=[], status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    return Api(client, db, fake_idp)


# --- The list ---


@pytest.mark.parametrize("sub", ["owner", "manager", "asha"])
def test_everyone_sees_the_rubrics_of_their_types(api: Api, sub: str) -> None:
    response = api.get(sub, "/v1/rubrics")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["type"] for i in items] == ["teaching", "reception"]  # the setup screen's order
    teaching, reception = items
    assert teaching["current_id"] == "teaching.school.v0.1"
    assert [v["id"] for v in teaching["versions"]] == ["teaching.school.v0.1"]
    assert reception["current_id"] == "reception.school.v0.2"
    assert reception["versions"] == [  # newest first
        {"id": "reception.school.v0.2", "version": "0.2", "in_use": True},
        {"id": "reception.school.v0.1", "version": "0.1", "in_use": False},
    ]
    assert reception["dimension_count"] > 0


def test_each_profile_sees_its_own_rubrics(api: Api) -> None:
    items = api.get("owner-b", "/v1/rubrics").json()["items"]
    assert {i["type"]: i["current_id"] for i in items} == {
        "reception": "reception.company.v0.1",
        "meeting": "meeting.company.v0.1",
        "sales": "sales.company.v0.2",
    }


def test_a_type_switched_off_is_not_listed(api: Api) -> None:
    api.db["tenants"].update_one({"_id": T}, {"$set": {"enabled_types": ["teaching"]}})
    assert [i["type"] for i in api.get("owner", "/v1/rubrics").json()["items"]] == ["teaching"]
    assert api.get("owner", "/v1/rubrics/reception.school.v0.2").status_code == 404


# --- One rubric ---


def test_a_rubric_in_full(api: Api) -> None:
    response = api.get("asha", "/v1/rubrics/teaching.school.v0.1")
    assert response.status_code == 200, response.text
    out = response.json()
    assert (out["id"], out["type"], out["version"], out["in_use"]) == ("teaching.school.v0.1", "teaching", "0.1", True)
    first = out["dimensions"][0]
    assert first["key"] == "concept_clarity" and first["name"] == "Concept clarity"
    assert first["weight"] == pytest.approx(0.25)
    assert first["min_quotes"] == 2
    assert first["definition"].startswith("The teacher states the main idea")
    assert [level["level"] for level in first["scale"]] == [1, 2, 3, 4, 5]
    assert first["scale"][0]["description"] and first["scale"][0]["example"]  # level 1 has an example
    assert first["scale"][1]["example"] is None  # level 2 has none in this rubric
    assert sum(d["weight"] for d in out["dimensions"]) == pytest.approx(1)
    assert out["previous_id"] is None and out["changes"] == []


def test_a_newer_version_says_what_changed(api: Api) -> None:
    out = api.get("owner", "/v1/rubrics/reception.school.v0.2").json()
    assert out["in_use"] is True
    assert out["previous_id"] == "reception.school.v0.1"
    assert out["changes"], "v0.2 differs from v0.1"
    assert all(set(c) == {"dimension", "item", "old", "new"} for c in out["changes"])
    older = api.get("owner", "/v1/rubrics/reception.school.v0.1").json()
    assert older["in_use"] is False


@pytest.mark.parametrize(
    "rubric_id",
    [
        "sales.company.v0.2",  # another profile's
        "teaching.company.v0.1",  # no such file
        "nope",
        "teaching.school.v0.1.yaml",
        "..%2Fpyproject",
        "teaching.school.v9.9",
    ],
)
def test_other_rubrics_are_not_found(api: Api, rubric_id: str) -> None:
    response = api.get("owner", f"/v1/rubrics/{rubric_id}")
    assert response.status_code == 404, response.text


def test_signed_out_callers_get_401(api: Api) -> None:
    assert api.client.get("/v1/rubrics").status_code == 401
    assert api.client.get("/v1/rubrics/teaching.school.v0.1").status_code == 401
