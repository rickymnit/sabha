"""Retrying or closing a failed recording (P7.8, owner's decision 2026-10-27: the tenant's owners and admins).

- POST /v1/recordings/{id}/retry {reason} (Idempotency-Key): the recording must be FAILED with an open dead letter
  (a pipeline failure no one has retried or closed yet). It goes back to where the failed stage starts
  (sabha_core.state.retry_status) with its outbox event, so the relay starts that stage again; earlier stages are
  not repeated. The dead letter is marked replayed; the audit log gets recording.retry with the reason.
- POST /v1/recordings/{id}/abandon {reason} (Idempotency-Key): the recording stays FAILED; the dead letter is
  marked abandoned so it cannot be retried; audit recording.abandon.
- A recording a reviewer closed (no dead letter), one not failed, one already retried or closed: 409. Anyone
  else: 403; another tenant's recording: 404.

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
from sabha_core.models import DeadLetter, IdentityLink, OutboxEvent, Person, Recording, Role, Tenant, Unit, User
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus
from sabha_workers.relay import routes

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, role)
    "owner": (T, "u-owner", Role.OWNER),
    "admin": (T, "u-admin", Role.ADMIN),
    "manager": (T, "u-manager", Role.MANAGER),
    "asha": (T, "u-asha", Role.STAFF),
    "owner-b": (B, "u-owner-b", Role.OWNER),
}
REASON = "The speech-to-text key was renewed."


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any

    def post(self, sub: str, rid: str, verb: str, key: str | None = None, **body: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}", "Idempotency-Key": key or uuid.uuid4().hex}
        return self.client.post(f"/v1/recordings/{rid}/{verb}", json={"reason": REASON, **body}, headers=headers)

    def recording(self, rid: str) -> dict[str, Any]:
        found = self.db["recordings"].find_one({"_id": rid})
        assert found is not None
        return found

    def letters(self, rid: str) -> list[dict[str, Any]]:
        return list(self.db["dlq"].find({"recording_id": rid}))

    def events(self, rid: str) -> list[dict[str, Any]]:
        return list(self.db["outbox"].find({"payload.recording_id": rid}))


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"retry_{uuid.uuid4().hex[:12]}"
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
    insert(db, "tenants", Tenant.from_profile("school", name="Other", plan=Plan.PILOT, id=B))
    insert(db, "units", Unit(id="unit-1", tenant_id=T, name="Class 1"))
    for sub, (tenant, user_id, role) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=["unit-1"] if role in (Role.MANAGER, Role.STAFF) else [],
                                 status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    return Api(client, db, fake_idp)


def failed(api: Api, stage: str = "transcribe", *, tenant: str = T, dead_letter: bool = True,
           status: RecordingStatus = RecordingStatus.FAILED) -> str:  # fmt: skip
    """A recording that failed in `stage` for good, with its dead letter (as the stage runner leaves it)."""
    rid = f"r-{uuid.uuid4().hex[:8]}"
    insert(api.db, "recordings", Recording(id=rid, tenant_id=tenant, type=ConversationType.TEACHING, status=status,
                                           status_reason="provider_auth", consent_ref="c", person_id="p-asha",
                                           unit_id="unit-1", file_name="Fractions.mp3"))  # fmt: skip
    if dead_letter:
        insert(api.db, "dlq", DeadLetter(tenant_id=tenant, recording_id=rid, stage=stage, task=f"sabha.{stage}",
                                         error_code="provider_auth", error_detail="403 invalid_api_key_error",
                                         attempts=5, args={"tenant_id": tenant, "recording_id": rid}))  # fmt: skip
    return rid


# --- Retry ---


@pytest.mark.parametrize(
    ("stage", "status", "task"),
    [("preprocess", "UPLOADED", "preprocess"), ("diarize", "DIARIZING", "diarize"),
     ("transcribe", "TRANSCRIBING", "transcribe"), ("analyze", "ANALYZING", "analyze")],
)  # fmt: skip
def test_a_retry_starts_the_failed_stage_again(api: Api, stage: str, status: str, task: str) -> None:
    rid = failed(api, stage)
    response = api.post("owner", rid, "retry")
    assert response.status_code == 200, response.text
    assert response.json() == {"recording_id": rid, "status": status, "stage": stage}
    assert api.recording(rid)["status"] == status
    [event] = api.events(rid)
    assert routes(OutboxEvent.model_validate(event)) == (task,)  # the relay starts exactly that stage
    [letter] = api.letters(rid)
    assert letter["replayed_at"] is not None and letter.get("abandoned_at") is None


def test_a_retry_is_audited_with_its_reason(api: Api) -> None:
    rid = failed(api)
    assert api.post("admin", rid, "retry").status_code == 200
    [entry] = api.db["audit_log"].find({"action": "recording.retry"})
    assert (entry["actor_user_id"], entry["target_id"]) == ("u-admin", rid)
    assert entry["meta"] == {"reason": REASON, "stage": "transcribe", "error_code": "provider_auth"}


def test_the_same_request_twice_starts_the_stage_once(api: Api) -> None:
    rid = failed(api)
    first = api.post("owner", rid, "retry", key="k-1")
    again = api.post("owner", rid, "retry", key="k-1")
    assert again.status_code == first.status_code == 200
    assert again.json() == first.json()
    assert len(api.events(rid)) == 1


def test_a_second_retry_is_refused_until_it_fails_again(api: Api) -> None:
    rid = failed(api)
    assert api.post("owner", rid, "retry").status_code == 200
    refused = api.post("owner", rid, "retry")
    assert refused.status_code == 409 and refused.json()["code"] == "not_failed"
    # It failed again: a new dead letter, so it can be retried again.
    api.db["recordings"].update_one({"_id": rid}, {"$set": {"status": "FAILED"}})
    insert(api.db, "dlq", DeadLetter(tenant_id=T, recording_id=rid, stage="transcribe", task="sabha.transcribe",
                                     error_code="provider_auth", attempts=5, args={}))  # fmt: skip
    assert api.post("owner", rid, "retry").status_code == 200
    assert len(api.events(rid)) == 2


def test_a_recording_a_reviewer_closed_cannot_be_retried(api: Api) -> None:
    rid = failed(api, dead_letter=False)  # NEEDS_REVIEW -> FAILED by a reviewer leaves no dead letter
    refused = api.post("owner", rid, "retry")
    assert refused.status_code == 409 and refused.json()["code"] == "not_retryable"
    assert api.recording(rid)["status"] == "FAILED"


@pytest.mark.parametrize("status", [RecordingStatus.COMPLETED, RecordingStatus.TRANSCRIBING,
                                    RecordingStatus.NEEDS_REVIEW])  # fmt: skip
def test_only_failed_recordings_can_be_retried(api: Api, status: RecordingStatus) -> None:
    rid = failed(api, status=status)
    refused = api.post("owner", rid, "retry")
    assert refused.status_code == 409 and refused.json()["code"] == "not_failed"
    assert api.recording(rid)["status"] == status.value


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_a_reason_is_required(api: Api, reason: str) -> None:
    rid = failed(api)
    assert api.post("owner", rid, "retry", reason=reason).status_code == 422
    assert api.recording(rid)["status"] == "FAILED"


# --- Abandon ---


def test_closing_a_failed_recording_for_good(api: Api) -> None:
    rid = failed(api)
    response = api.post("owner", rid, "abandon", reason="The audio was recorded in the wrong room.")
    assert response.status_code == 200, response.text
    assert response.json() == {"recording_id": rid, "status": "FAILED", "stage": "transcribe"}
    assert api.recording(rid)["status"] == "FAILED"
    [letter] = api.letters(rid)
    assert letter["abandoned_at"] is not None and letter["replayed_at"] is None
    [entry] = api.db["audit_log"].find({"action": "recording.abandon"})
    assert entry["meta"]["reason"] == "The audio was recorded in the wrong room."
    assert api.events(rid) == []  # nothing starts
    refused = api.post("owner", rid, "retry")
    assert refused.status_code == 409 and refused.json()["code"] == "not_retryable"


# --- Who ---


@pytest.mark.parametrize("sub", ["manager", "asha"])
@pytest.mark.parametrize("verb", ["retry", "abandon"])
def test_only_owners_and_admins(api: Api, sub: str, verb: str) -> None:
    rid = failed(api)
    refused = api.post(sub, rid, verb)
    assert refused.status_code == 403
    assert api.recording(rid)["status"] == "FAILED"
    assert api.letters(rid)[0]["replayed_at"] is None


@pytest.mark.parametrize("verb", ["retry", "abandon"])
def test_another_tenants_recording_is_not_found(api: Api, verb: str) -> None:
    rid = failed(api, tenant=B)
    assert api.post("owner", rid, verb).status_code == 404
    assert api.recording(rid)["status"] == "FAILED"


def test_processing_shows_the_failure_and_whether_it_can_be_retried(api: Api) -> None:
    rid = failed(api)
    get = lambda: api.client.get(f"/v1/recordings/{rid}/processing",  # noqa: E731
                                 headers={"Authorization": f"Bearer {api.idp.token('admin')}"}).json()  # fmt: skip
    before = get()
    assert before["can_retry"] is True
    assert before["failure"]["state"] == "open" and before["failure"]["stage"] == "transcribe"
    assert before["ai"] == {"calls": 0, "cost_usd": None, "unpriced_calls": 0}
    api.post("owner", rid, "retry")
    after = get()
    assert after["can_retry"] is False and after["failure"]["state"] == "retried"
