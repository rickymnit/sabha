"""POST /v1/recordings and /parts (plan task P2.1) against real MongoDB and RustFS: the browser's upload is replayed
by PUTting bytes to the presigned URLs, so the URLs are proven to work, not just to exist.
"""

from __future__ import annotations

import hashlib
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
from sabha_core.models import (
    Analysis,
    IdentityLink,
    LlmCall,
    OutboxEvent,
    Person,
    Recording,
    RelayState,
    Role,
    Tenant,
    Transcript,
    Unit,
    User,
)
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS, SyncSystemRepo
from sabha_core.state import RecordingStatus
from sabha_workers.relay import Relay

pytestmark = pytest.mark.integration

MIB = 1024**2
PART = 5 * MIB  # the smallest part size S3 allows; keeps the test uploads small

USERS = {  # subject -> (tenant, user id, role)
    "owner-a": ("tenant-a", "u-owner-a", Role.OWNER),
    "staff-a": ("tenant-a", "u-staff-a", Role.STAFF),
    "staff-nobody": ("tenant-a", "u-staff-nobody", Role.STAFF),  # no person linked
    "owner-b": ("tenant-b", "u-owner-b", Role.OWNER),
}


def seed(db: Database[dict[str, Any]], issuer: str) -> None:
    for tenant_id in ("tenant-a", "tenant-b"):
        tenant = Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id)
        db.tenants.insert_one(tenant.model_dump(by_alias=True))
    for sub, (tenant_id, user_id, role) in USERS.items():
        email = f"{user_id}@example.com"
        db.users.insert_one(
            User(id=user_id, tenant_id=tenant_id, email=email, name=user_id, role=role, status="active").model_dump(
                by_alias=True
            )
        )
        link = IdentityLink(tenant_id=tenant_id, issuer=issuer, subject=sub, email=email, user_id=user_id)
        db.identities.insert_one(link.model_dump(by_alias=True))
    db.units.insert_one(Unit(id="unit-a", tenant_id="tenant-a", name="Primary").model_dump(by_alias=True))
    for person in (
        Person(id="p-staff-a", tenant_id="tenant-a", name="Asha", unit_id="unit-a", user_id="u-staff-a"),
        Person(id="p-other", tenant_id="tenant-a", name="Bina"),
        Person(id="p-b", tenant_id="tenant-b", name="Chitra"),
    ):
        db.people.insert_one(person.model_dump(by_alias=True))


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any
    s3: Any
    bucket: str = "sabha-audio"

    def headers(self, sub: str, key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    def create(self, sub: str, body: dict[str, Any], key: str | None = None) -> httpx.Response:
        return self.client.post("/v1/recordings", json=body, headers=self.headers(sub, key or str(uuid.uuid4())))

    def parts(self, sub: str, recording_id: str, numbers: list[int]) -> httpx.Response:
        return self.client.post(
            f"/v1/recordings/{recording_id}/parts", json={"part_numbers": numbers}, headers=self.headers(sub)
        )


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"rec_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def api(
    make_client: Any,
    mongo_uri: str,
    mongo_replica_set: MongoClient[dict[str, Any]],
    shared_db: str,
    fake_idp: Any,
    s3_storage: Any,
) -> Api:
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    client = make_client(
        resources=open_resources,
        token_verifier=fake_idp.verifier(),
        mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=shared_db,
        redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url=s3_storage.endpoint_url,
        s3_access_key_id=s3_storage.access_key_id,
        s3_secret_access_key=s3_storage.secret_access_key,
        upload_part_size_bytes=PART,
        asr_provider="sarvam",  # priced at Sarvam's published rate (sabha_asr.pricing); never called here
        sarvam_api_key="test-key",  # pragma: allowlist secret  (a placeholder; nothing is sent to Sarvam)
        usd_inr_rate=90.0,
    )
    seed(db, client.app.state.settings.oidc_issuer)
    return Api(client, db, fake_idp, s3_storage.client())


LESSON = {
    "type": "teaching",
    "file_name": "Class 7B (Fractions).mp3",
    "size_bytes": PART + 1,
    "content_type": "audio/mpeg",
}


def problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- Create ---


def test_the_upload_keeps_its_expected_cost_and_the_actual_comes_from_usage(api: Api) -> None:
    def cost(path: str) -> dict[str, Any]:
        response = api.client.get(path, headers=api.headers("owner-a"))
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    # No history yet: speech-to-text at Sarvam's published Rs 0.49/min for the whole length; no LLM figure, no total
    first = cost("/v1/costs/estimate?type=teaching&duration_ms=600000")["estimate"]
    assert (first["asr_inr"], first["llm_inr"], first["total_inr"], first["history_n"]) == (4.9, None, None, 0)

    # History: a finished 10-minute lesson, 6 minutes of speech, whose analysis cost $0.02
    api.db.recordings.insert_one(Recording(
        id="r-done", tenant_id="tenant-a", type=ConversationType.TEACHING, status=RecordingStatus.COMPLETED,
        consent_ref="c", duration_ms=600_000, speech_ms=360_000,
    ).model_dump(by_alias=True))  # fmt: skip
    api.db.analyses.insert_one(Analysis(
        tenant_id="tenant-a", recording_id="r-done", version="v1", conversation_type=ConversationType.TEACHING,
        rubric_id="teaching.school.v0.1", rubric_version="0.1", rubric_hash="h", report_key="k", status="COMPLETED",
        verified_share=1.0, cost_usd=0.02,
    ).model_dump(by_alias=True))  # fmt: skip

    created = api.create("owner-a", {**LESSON, "expected_duration_ms": 1_200_000})
    rid = created.json()["recording_id"]
    kept = cost(f"/v1/recordings/{rid}/cost")["estimate"]
    # 20 min x 60 % speech x Rs 0.49 = 5.88; $0.002/min x 20 min x Rs 90 = 3.60
    assert (kept["asr_inr"], kept["llm_inr"], kept["total_inr"]) == (5.88, 3.6, 9.48)
    assert (kept["speech_share"], kept["history_n"], kept["usd_inr_rate"]) == (0.6, 1, 90.0)

    # Actual: what was sent to speech-to-text, and the LLM calls' recorded cost
    api.db.transcripts.insert_one(Transcript(
        tenant_id="tenant-a", recording_id=rid, version="transcript@v1", storage_key="k", asr_model="m",
        word_timing="approximate", word_count=1, utterance_count=1, rubric_id="teaching.school.v0.1",
        asr_billed_ms=780_000, asr_cost_inr=6.37,
    ).model_dump(by_alias=True))  # fmt: skip
    for usd in (0.01, 0.015):
        api.db.llm_calls.insert_one(LlmCall(
            tenant_id="tenant-a", recording_id=rid, task="score", provider="openai", model="gpt-6-luna",
            prompt_hash="p", status="ok", cost_usd=usd, latency_ms=1, attempt=1,
        ).model_dump(by_alias=True))  # fmt: skip
    actual = cost(f"/v1/recordings/{rid}/cost")["actual"]
    assert (actual["asr_inr"], actual["llm_inr"], actual["total_inr"], actual["final"]) == (6.37, 2.25, 8.62, False)

    # One call without a price: the LLM part is unknown rather than understated
    api.db.llm_calls.insert_one(
        LlmCall(
            tenant_id="tenant-a",
            recording_id=rid,
            task="score",
            provider="x",
            model="y",
            prompt_hash="p",
            status="ok",
            latency_ms=1,
            attempt=1,
        ).model_dump(by_alias=True)
    )
    actual = cost(f"/v1/recordings/{rid}/cost")["actual"]
    assert (actual["llm_inr"], actual["total_inr"], actual["llm_unpriced_calls"]) == (None, None, 1)


def test_create_returns_presigned_parts_and_records_the_recording(api: Api) -> None:
    response = api.create("owner-a", {**LESSON, "person_id": "p-other", "consent_ref": "consent-7b"})
    assert response.status_code == 201, response.text
    body = response.json()
    rid = body["recording_id"]
    assert (body["status"], body["part_size"], body["part_count"]) == ("CREATED", PART, 2)
    assert [p["part_number"] for p in body["parts"]] == [1, 2]
    doc = api.db.recordings.find_one({"_id": rid})
    assert doc is not None
    assert doc["tenant_id"] == "tenant-a" and doc["status"] == "CREATED"
    assert doc["storage_key"] == f"tenant-a/{rid}/original/Class_7B_Fractions.mp3"
    assert (doc["person_id"], doc["consent_ref"], doc["created_by"]) == ("p-other", "consent-7b", "u-owner-a")
    assert doc["upload_id"] == body["upload_id"]


def test_the_presigned_urls_accept_the_upload(api: Api) -> None:
    body = api.create("owner-a", LESSON).json()
    data = [b"a" * PART, b"b"]
    etags = []
    for part, chunk in zip(body["parts"], data, strict=True):
        put = httpx.put(part["url"], content=chunk)
        assert put.status_code == 200, put.text
        etags.append({"PartNumber": part["part_number"], "ETag": put.headers["etag"]})
    doc = api.db.recordings.find_one({"_id": body["recording_id"]})
    assert doc is not None
    key = doc["storage_key"]
    api.s3.complete_multipart_upload(
        Bucket=api.bucket, Key=key, UploadId=body["upload_id"], MultipartUpload={"Parts": etags}
    )  # P2.2 does this through the API
    assert api.s3.head_object(Bucket=api.bucket, Key=key)["ContentLength"] == PART + 1


def test_every_create_is_audited(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    entry = api.db.audit_log.find_one({"target_id": rid})
    assert entry is not None
    assert (entry["tenant_id"], entry["action"], entry["actor_user_id"]) == (
        "tenant-a",
        "recording.create",
        "u-owner-a",
    )


def test_a_replay_returns_the_same_upload(api: Api) -> None:
    first = api.create("owner-a", LESSON, key="same")
    second = api.create("owner-a", LESSON, key="same")
    assert second.json() == first.json() and second.headers["idempotent-replayed"] == "true"
    assert api.db.recordings.count_documents({}) == 1


def test_a_type_the_tenant_has_not_enabled_is_refused(api: Api) -> None:
    problem(api.create("owner-a", {**LESSON, "type": "sales"}), 422, "type_not_enabled")


@pytest.mark.parametrize(
    ("file_name", "content_type"),
    [("lesson.exe", "application/octet-stream"), ("lesson.mp3", "video/mp4"), ("lesson", "audio/mpeg")],
)
def test_unsupported_formats_are_refused(api: Api, file_name: str, content_type: str) -> None:
    body = {**LESSON, "file_name": file_name, "content_type": content_type}
    problem(api.create("owner-a", body), 422, "unsupported_format")


def test_content_type_parameters_are_ignored(api: Api) -> None:
    body = {**LESSON, "file_name": "call.webm", "content_type": "audio/webm;codecs=opus"}
    assert api.create("owner-a", body).status_code == 201


def test_oversize_files_are_refused(api: Api) -> None:
    problem(api.create("owner-a", {**LESSON, "size_bytes": 1024**3 + 1}), 422, "file_too_large")


def test_people_and_units_must_belong_to_the_tenant(api: Api) -> None:
    problem(api.create("owner-a", {**LESSON, "person_id": "p-b"}), 422, "unknown_person")
    problem(api.create("owner-a", {**LESSON, "unit_id": "nope"}), 422, "unknown_unit")


@pytest.mark.parametrize(
    "extra", [{"id": "x"}, {"status": "UPLOADED"}, {"storage_key": "tenant-b/x"}, {"tenant_id": "b"}]
)
def test_clients_cannot_choose_ids_status_or_keys(api: Api, extra: dict[str, Any]) -> None:
    problem(api.create("owner-a", {**LESSON, **extra}), 422, "validation_error")


# --- Staff upload only their own recordings ---


def test_staff_uploads_are_for_their_own_person(api: Api) -> None:
    rid = api.create("staff-a", LESSON).json()["recording_id"]
    doc = api.db.recordings.find_one({"_id": rid})
    assert doc is not None and (doc["person_id"], doc["unit_id"]) == ("p-staff-a", "unit-a")


def test_staff_cannot_upload_for_a_colleague(api: Api) -> None:
    problem(api.create("staff-a", {**LESSON, "person_id": "p-other"}), 403, "person_not_allowed")


def test_staff_without_a_linked_person_cannot_upload(api: Api) -> None:
    problem(api.create("staff-nobody", LESSON), 403, "no_linked_person")


# --- Fresh part URLs for resumed uploads ---


def test_parts_returns_fresh_urls_for_the_requested_parts(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    response = api.parts("owner-a", rid, [2])
    assert response.status_code == 200, response.text
    (part,) = response.json()["parts"]
    assert part["part_number"] == 2 and httpx.put(part["url"], content=b"b").status_code == 200


def test_parts_beyond_the_upload_are_refused(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    problem(api.parts("owner-a", rid, [3]), 422, "invalid_part_number")


def test_another_tenant_cannot_get_part_urls(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    problem(api.parts("owner-b", rid, [1]), 404, "not_found")


def test_staff_cannot_get_part_urls_for_someone_elses_upload(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    problem(api.parts("staff-a", rid, [1]), 404, "not_found")


def test_parts_only_while_the_upload_is_open(api: Api) -> None:
    rid = api.create("owner-a", LESSON).json()["recording_id"]
    api.db.recordings.update_one({"_id": rid}, {"$set": {"status": "UPLOADED"}})
    problem(api.parts("owner-a", rid, [1]), 409, "upload_not_open")


def test_keys_are_always_under_the_callers_tenant(api: Api) -> None:
    for sub in ("owner-a", "owner-b"):
        rid = api.create(sub, LESSON).json()["recording_id"]
        doc = api.db.recordings.find_one({"_id": rid})
        assert doc is not None and doc["storage_key"].startswith(f"{doc['tenant_id']}/{rid}/original/")


# --- Complete (P2.2) ---


@dataclass
class Uploaded:
    recording_id: str
    parts: list[dict[str, Any]]
    sha256: str


def upload(api: Api, sub: str = "owner-a", content: bytes = b"a" * PART + b"b", **body: Any) -> Uploaded:
    """Create a recording for `content` and PUT its parts, as the browser does."""
    created = api.create(
        sub, {**LESSON, "consent_ref": "consent-7b", **body, "size_bytes": body.get("size_bytes", len(content))}
    )
    assert created.status_code == 201, created.text
    out = created.json()
    parts = []
    for part in out["parts"]:
        start = (part["part_number"] - 1) * PART
        put = httpx.put(part["url"], content=content[start : start + PART])
        assert put.status_code == 200, put.text
        parts.append({"part_number": part["part_number"], "etag": put.headers["etag"]})
    return Uploaded(out["recording_id"], parts, hashlib.sha256(content).hexdigest())


def complete(api: Api, up: Uploaded, sub: str = "owner-a", **extra: Any) -> httpx.Response:
    body = {"parts": up.parts, "sha256": up.sha256, **extra}
    return api.client.post(f"/v1/recordings/{up.recording_id}/complete", json=body, headers=api.headers(sub))


def test_complete_moves_the_recording_to_uploaded(api: Api) -> None:
    up = upload(api)
    response = complete(api, up)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "recording_id": up.recording_id,
        "status": "UPLOADED",
        "awaiting_consent": False,
        "duplicate_of": None,
    }
    doc = api.db.recordings.find_one({"_id": up.recording_id})
    assert doc is not None
    assert (doc["status"], doc["status_reason"], doc["sha256"]) == ("UPLOADED", "upload_complete", up.sha256)
    assert api.s3.head_object(Bucket=api.bucket, Key=doc["storage_key"])["ContentLength"] == PART + 1


def test_without_consent_the_recording_waits(api: Api) -> None:
    up = upload(api, consent_ref=None)
    body = complete(api, up).json()
    assert (body["status"], body["awaiting_consent"]) == ("UPLOADED", True)


def test_complete_is_safe_to_retry(api: Api) -> None:
    up = upload(api)
    first = complete(api, up)
    again = complete(api, up)
    assert again.status_code == 200 and again.json() == first.json()


def test_every_part_is_needed(api: Api) -> None:
    up = upload(api)
    up.parts = up.parts[:1]
    problem(complete(api, up), 422, "invalid_parts")


def test_a_wrong_etag_is_refused(api: Api) -> None:
    up = upload(api)
    up.parts[0]["etag"] = '"0123456789abcdef0123456789abcdef"'  # pragma: allowlist secret  (a made-up ETag)
    problem(complete(api, up), 422, "invalid_parts")
    doc = api.db.recordings.find_one({"_id": up.recording_id})
    assert doc is not None and doc["status"] == "CREATED"


def test_a_size_mismatch_discards_the_upload(api: Api) -> None:
    up = upload(api, content=b"a" * PART + b"b", size_bytes=PART + 10)
    problem(complete(api, up), 422, "size_mismatch")
    doc = api.db.recordings.find_one({"_id": up.recording_id})
    assert doc is not None and doc["status"] == "CREATED" and doc["upload_id"] is None
    with pytest.raises(api.s3.exceptions.ClientError):
        api.s3.head_object(Bucket=api.bucket, Key=doc["storage_key"])
    problem(api.parts("owner-a", up.recording_id, [1]), 409, "upload_not_open")


def test_a_duplicate_is_held_until_confirmed(api: Api) -> None:
    original = upload(api)
    assert complete(api, original).status_code == 200
    copy = upload(api)
    response = complete(api, copy)
    problem(response, 409, "duplicate_recording")
    assert response.json()["duplicate_of"] == original.recording_id
    doc = api.db.recordings.find_one({"_id": copy.recording_id})
    assert doc is not None and doc["status"] == "UPLOADED" and doc["duplicate_confirmed"] is False

    problem(complete(api, copy), 409, "duplicate_recording")  # a plain retry is still held
    forced = complete(api, copy, force=True)
    assert forced.status_code == 200 and forced.json()["duplicate_of"] == original.recording_id
    doc = api.db.recordings.find_one({"_id": copy.recording_id})
    assert doc is not None and doc["duplicate_confirmed"] is True
    assert complete(api, copy).status_code == 200  # confirmed: retries succeed


def test_force_on_the_first_call_confirms_at_once(api: Api) -> None:
    original = upload(api)
    complete(api, original)
    copy = upload(api)
    assert complete(api, copy, force=True).status_code == 200


def test_duplicates_are_per_tenant(api: Api) -> None:
    complete(api, upload(api, "owner-a"))
    assert complete(api, upload(api, "owner-b"), "owner-b").status_code == 200


def test_a_failed_recording_is_not_a_duplicate(api: Api) -> None:
    original = upload(api)
    complete(api, original)
    api.db.recordings.update_one({"_id": original.recording_id}, {"$set": {"status": "FAILED"}})
    assert complete(api, upload(api)).status_code == 200


def test_another_tenant_cannot_complete(api: Api) -> None:
    problem(complete(api, upload(api), "owner-b"), 404, "not_found")


def test_staff_cannot_complete_a_colleagues_upload(api: Api) -> None:
    problem(complete(api, upload(api), "staff-a"), 404, "not_found")


def test_staff_complete_their_own_upload(api: Api) -> None:
    up = upload(api, "staff-a")
    assert complete(api, up, "staff-a").status_code == 200


@pytest.mark.parametrize("sha", ["", "xyz", "a" * 63, "g" * 64])
def test_the_checksum_must_be_sha256_hex(api: Api, sha: str) -> None:
    up = upload(api)
    up.sha256 = sha
    problem(complete(api, up), 422, "validation_error")


def test_a_completed_upload_cannot_complete_with_another_file(api: Api) -> None:
    up = upload(api)
    complete(api, up)
    up.sha256 = "0" * 64
    problem(complete(api, up), 409, "upload_not_open")


# --- The outbox event and the relay (P2.5) ---


class RecordingDispatcher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, task: str, event: OutboxEvent) -> None:
        self.sent.append((task, event.payload["recording_id"]))


class NoPublisher:
    def publish(self, channel: str, message: str) -> None:
        pass


def relay_all(api: Api) -> list[tuple[str, str]]:
    dispatcher = RecordingDispatcher()
    relay = Relay(
        SyncSystemRepo(api.db, "outbox", OutboxEvent),
        SyncSystemRepo(api.db, "relay_state", RelayState),
        dispatcher,
        NoPublisher(),
    )
    relay.sweep(older_than=timedelta(0))
    return dispatcher.sent


def events(api: Api, recording_id: str) -> list[dict[str, Any]]:
    return list(api.db.outbox.find({"payload.recording_id": recording_id}).sort("created_at", 1))


def test_complete_writes_the_upload_event_in_the_same_change(api: Api) -> None:
    up = upload(api)
    complete(api, up)
    (event,) = events(api, up.recording_id)
    assert (event["tenant_id"], event["type"]) == ("tenant-a", "recording.uploaded")
    assert event["payload"]["meta"]["ready"] is True


def test_completing_an_upload_starts_preprocessing(api: Api) -> None:
    up = upload(api)
    complete(api, up)
    assert relay_all(api) == [("preprocess", up.recording_id)]


def test_a_recording_without_consent_is_not_processed(api: Api) -> None:
    up = upload(api, consent_ref=None)
    complete(api, up)
    assert events(api, up.recording_id)[0]["payload"]["meta"]["ready"] is False
    assert relay_all(api) == []


def test_a_held_duplicate_is_processed_only_once_confirmed(api: Api) -> None:
    original = upload(api)
    complete(api, original)
    relay_all(api)
    copy = upload(api)
    complete(api, copy)
    assert relay_all(api) == []  # held
    complete(api, copy, force=True)
    complete(api, copy, force=True)  # confirming again writes no second event
    assert [e["type"] for e in events(api, copy.recording_id)] == ["recording.uploaded", "recording.ready"]
    assert relay_all(api) == [("preprocess", copy.recording_id)]
