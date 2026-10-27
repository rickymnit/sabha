"""The sidebar's numbers (P6.2, P7.2): this month's audio hours and the recordings per conversation type.

- GET /v1/usage (owners and admins): the plan, the audio hours of recordings uploaded this calendar month in India
  time (their measured duration; not yet measured counts nothing), the allowance Sabha set for the tenant or null
  when none is set (never an invented number, golden rule 6), the quota state and the reset time.
- GET /v1/recordings/counts (everyone signed in): how many recordings of each type the caller may see, the same
  recordings the list shows, so a count and the list it opens always agree.

The permission matrix (tests/security) covers both routes for every caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Person, Recording, Role, Tenant, Unit, User, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import IST, Plan, month_bounds
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, role, units)
    "owner": (T, "u-owner", Role.OWNER, []),
    "admin": (T, "u-admin", Role.ADMIN, []),
    "manager": (T, "u-manager", Role.MANAGER, ["unit-1"]),
    "asha": (T, "u-asha", Role.STAFF, ["unit-1"]),
    "owner-b": (B, "u-owner-b", Role.OWNER, []),
}
HOUR_MS = 3_600_000


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any

    def get(self, sub: str, path: str) -> httpx.Response:
        return self.client.get(path, headers={"Authorization": f"Bearer {self.idp.token(sub)}"})


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"usage_{uuid.uuid4().hex[:12]}"
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
    insert(db, "tenants", Tenant.from_profile("school", name="Sunrise", plan=Plan.STARTER, id=T))
    insert(db, "tenants", Tenant.from_profile("company", name="Brightpath", plan=Plan.PILOT, id=B))
    insert(db, "units", Unit(id="unit-1", tenant_id=T, name="Class 1"))
    insert(db, "units", Unit(id="unit-2", tenant_id=T, name="Class 2"))
    for sub, (tenant, user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    insert(db, "people", Person(id="p-ravi", tenant_id=T, name="Ravi", unit_id="unit-2"))
    return Api(client, db, fake_idp)


def recording(api: Api, *, tenant: str = T, type: str = "teaching", person: str = "p-asha", unit: str = "unit-1",
              duration_ms: int | None = HOUR_MS, created_at: datetime | None = None,
              status: RecordingStatus = RecordingStatus.COMPLETED) -> None:  # fmt: skip
    insert(api.db, "recordings", Recording(tenant_id=tenant, type=ConversationType(type), status=status,
                                           consent_ref="c", person_id=person, unit_id=unit, file_name="x.mp3",
                                           duration_ms=duration_ms, created_at=created_at or utc_now()))  # fmt: skip


# --- Usage ---


def test_usage_adds_up_this_months_measured_audio(api: Api) -> None:
    start, end = month_bounds(utc_now())
    recording(api, duration_ms=2 * HOUR_MS, created_at=start)  # the first moment of the month, India time
    recording(api, duration_ms=HOUR_MS // 2, type="reception", person="p-ravi", unit="unit-2")
    recording(api, duration_ms=None, status=RecordingStatus.PREPROCESSING)  # not measured yet
    recording(api, duration_ms=5 * HOUR_MS, created_at=start - timedelta(seconds=1))  # last month
    recording(api, tenant=B, type="sales", duration_ms=7 * HOUR_MS)  # another tenant
    response = api.get("owner", "/v1/usage")
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["plan"] == "starter"
    assert out["used_hours"] == pytest.approx(2.5)
    assert out["allowance_hours"] is None  # Sabha has not set one: no invented number
    assert out["state"] is None
    assert out["message"] is None
    assert datetime.fromisoformat(out["resets_at"]) == end
    assert datetime.fromisoformat(out["resets_at"]).astimezone(IST).day == 1


def test_usage_against_the_allowance_sabha_set(api: Api) -> None:
    api.db["tenants"].update_one({"_id": T}, {"$set": {"audio_hours_allowance": 3}})
    recording(api, duration_ms=int(2.5 * HOUR_MS))
    out = api.get("admin", "/v1/usage").json()
    assert out["allowance_hours"] == 3
    assert out["state"] == "warning"  # past 80 %
    assert "2.5 of this month's 3 audio hours" in out["message"]


def test_the_allowance_is_never_zero_or_negative() -> None:
    with pytest.raises(ValueError, match="audio_hours_allowance"):
        Tenant.from_profile("school", name="x", plan=Plan.PILOT, audio_hours_allowance=0)


@pytest.mark.parametrize("sub", ["manager", "asha"])
def test_only_owners_and_admins_see_usage(api: Api, sub: str) -> None:
    response = api.get(sub, "/v1/usage")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_a_month_starts_in_india_time() -> None:
    # 1 Nov 2026 00:00 IST is 31 Oct 18:30 UTC: a recording at 19:00 UTC on 31 Oct belongs to November.
    start, end = month_bounds(datetime(2026, 10, 31, 19, 0, tzinfo=UTC))
    assert start == datetime(2026, 10, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 11, 30, 18, 30, tzinfo=UTC)


# --- Counts per type ---


def test_counts_follow_what_each_caller_may_see(api: Api) -> None:
    recording(api)
    recording(api, status=RecordingStatus.TRANSCRIBING)
    recording(api, type="reception")
    recording(api, person="p-ravi", unit="unit-2")
    recording(api, tenant=B, type="sales")
    assert api.get("owner", "/v1/recordings/counts").json() == {"by_type": {"teaching": 3, "reception": 1}}
    assert api.get("manager", "/v1/recordings/counts").json() == {"by_type": {"teaching": 2, "reception": 1}}
    assert api.get("asha", "/v1/recordings/counts").json() == {"by_type": {"teaching": 2, "reception": 1}}
    assert api.get("owner-b", "/v1/recordings/counts").json() == {"by_type": {"sales": 1}}


def test_counts_match_the_list_they_open(api: Api) -> None:
    for _ in range(3):
        recording(api, type="reception")
    counted = api.get("owner", "/v1/recordings/counts").json()["by_type"]["reception"]
    listed = api.get("owner", "/v1/recordings?type=reception&limit=100").json()["items"]
    assert counted == len(listed) == 3


def test_counts_are_empty_with_no_recordings(api: Api) -> None:
    assert api.get("owner", "/v1/recordings/counts").json() == {"by_type": {}}
