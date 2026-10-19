"""POST /v1/recordings and /parts (plan task P2.1) against real MongoDB and RustFS: the browser's upload is replayed
by PUTting bytes to the presigned URLs, so the URLs are proven to work, not just to exist.
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
from sabha_core.models import IdentityLink, Person, Role, Tenant, Unit, User
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS

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
