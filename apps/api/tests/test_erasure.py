"""Erasure on request (P7.3, DPDP; owner's decision 2026-10-27: owners only, one recording or one person).

POST /v1/erasure {scope, id, reason, confirm}: without confirm it only counts; with it, everything stored for the
scope goes, in storage and in every collection, and one audit entry (data.erase, counts only) records it. Nothing
of anyone else's is touched. The permission matrix covers who may call it.
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
from sabha_core.models import (
    Analysis,
    Dispute,
    IdentityLink,
    LlmCall,
    OutboxEvent,
    Person,
    Recording,
    Role,
    Score,
    StageRun,
    Tenant,
    Transcript,
    Unit,
    User,
    utc_now,
)  # fmt: skip
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T, B = "tenant-a", "tenant-b"
AUDIO, ARTEFACTS = "sabha-audio", "sabha-artefacts"
RUBRIC = "teaching.school.v0.1"
PER_RECORDING = ("recordings", "transcripts", "analyses", "scores", "disputes", "stage_runs", "llm_calls")


@dataclass
class Api:
    client: TestClient
    db: Database[dict[str, Any]]
    idp: Any
    s3: Any

    def erase(self, scope: str, target: str, *, confirm: bool, sub: str = "owner") -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.idp.token(sub)}", "Idempotency-Key": uuid.uuid4().hex}
        body = {"scope": scope, "id": target, "reason": "The teacher asked for her data to be erased.",
                "confirm": confirm}  # fmt: skip
        return self.client.post("/v1/erasure", json=body, headers=headers)

    def files(self, tenant: str, rid: str) -> int:
        return sum(self.s3.list_objects_v2(Bucket=b, Prefix=f"{tenant}/{rid}/").get("KeyCount", 0)
                   for b in (AUDIO, ARTEFACTS))  # fmt: skip

    def documents(self, rid: str) -> int:
        return sum(self.db[c].count_documents({"_id" if c == "recordings" else "recording_id": rid})
                   for c in PER_RECORDING) + self.db.outbox.count_documents({"payload.recording_id": rid})  # fmt: skip


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"erase_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


def insert(db: Database[dict[str, Any]], doc: Any, collection: str) -> None:
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
    for tenant in (T, B):
        insert(db, Tenant.from_profile("school", name=tenant, plan=Plan.PILOT, id=tenant), "tenants")
        insert(db, Unit(id=f"unit-{tenant}", tenant_id=tenant, name="Class 1"), "units")
    for sub, tenant, uid, role in (("owner", T, "u-owner", Role.OWNER), ("asha", T, "u-asha", Role.STAFF),
                                   ("owner-b", B, "u-owner-b", Role.OWNER)):  # fmt: skip
        insert(db, User(id=uid, tenant_id=tenant, email=f"{sub}@x.example", name=sub, role=role, status="active"),
               "users")  # fmt: skip
        insert(db, IdentityLink(tenant_id=tenant, issuer=issuer, subject=sub, email=f"{sub}@x.example", user_id=uid),
               "identities")  # fmt: skip
    insert(db, Person(id="p-asha", tenant_id=T, name="Asha", unit_id=f"unit-{T}", user_id="u-asha"), "people")
    insert(db, Person(id="p-ravi", tenant_id=T, name="Ravi", unit_id=f"unit-{T}"), "people")
    insert(db, Person(id="p-b", tenant_id=B, name="Bina", unit_id=f"unit-{B}"), "people")
    return Api(client, db, fake_idp, s3_storage.client())


def full_recording(api: Api, person: str, tenant: str = T) -> str:
    """A finished recording with every kind of stored record and file."""
    rid = f"r{uuid.uuid4().hex[:10]}"
    now = utc_now()
    docs = [
        (Recording(id=rid, tenant_id=tenant, type=ConversationType.TEACHING, status=RecordingStatus.COMPLETED,
                   consent_ref="c", person_id=person, unit_id=f"unit-{tenant}", file_name="Asha lesson.mp3"),
         "recordings"),
        (Transcript(tenant_id=tenant, recording_id=rid, version="transcript@v1", storage_key="k", asr_model="f",
                    word_timing="approximate", word_count=1, utterance_count=1, roles={}, rubric_id=RUBRIC),
         "transcripts"),
        (Analysis(id=f"an-{rid}", tenant_id=tenant, recording_id=rid, version="v1", person_id=person,
                  unit_id=f"unit-{tenant}", conversation_type=ConversationType.TEACHING,
                  rubric_id="teaching.school.v0.1", rubric_version="0.1", rubric_hash="h", report_key="k",
                  status="COMPLETED", overall_score=3.0, verified_share=1.0), "analyses"),
        (Score(tenant_id=tenant, analysis_id=f"an-{rid}", recording_id=rid, person_id=person, dimension="d", name="D",
               weight=1.0, score=3, verified=True), "scores"),
        (Dispute(tenant_id=tenant, analysis_id=f"an-{rid}", recording_id=rid, person_id=person, dimension="d",
                 dimension_name="D", ai_score=3, current_score=3, proposed_score=4, raised_by="u-asha",
                 comment="I asked three questions."), "disputes"),
        (StageRun(tenant_id=tenant, recording_id=rid, stage="analyze", version="v1", attempt=1, worker="w",
                  started_at=now), "stage_runs"),
        (LlmCall(tenant_id=tenant, recording_id=rid, task="judge", provider="openai", model="m", prompt_hash="h",
                 status="ok", latency_ms=1, attempt=1), "llm_calls"),
        (OutboxEvent(tenant_id=tenant, type="recording.completed", payload={"recording_id": rid}), "outbox"),
    ]  # fmt: skip
    for doc, collection in docs:
        insert(api.db, doc, collection)
    api.s3.put_object(Bucket=AUDIO, Key=f"{tenant}/{rid}/original/Asha_lesson.mp3", Body=b"a")
    for name in ("preprocess@v2/playback.opus", "transcribe@v1/transcript@v1.json", "analyze@v1/analysis@v1.json"):
        api.s3.put_object(Bucket=ARTEFACTS, Key=f"{tenant}/{rid}/{name}", Body=b"x")
    return rid


def test_a_recording_is_counted_then_erased_and_nothing_else_is_touched(api: Api) -> None:
    target, sibling, other_tenant = (
        full_recording(api, "p-asha"),
        full_recording(api, "p-asha"),
        full_recording(api, "p-b", B),
    )

    counted = api.erase("recording", target, confirm=False)
    assert counted.status_code == 200, counted.text
    assert counted.json()["erased"] is False and counted.json()["recordings"] == 1
    assert counted.json()["files"] == 4
    assert api.documents(target) == 8 and api.files(T, target) == 4  # a count deletes nothing

    erased = api.erase("recording", target, confirm=True)
    assert erased.status_code == 200, erased.text
    assert erased.json()["erased"] is True
    assert api.documents(target) == 0 and api.files(T, target) == 0
    for tenant, rid in ((T, sibling), (B, other_tenant)):
        assert api.documents(rid) == 8 and api.files(tenant, rid) == 4
    [entry] = api.db.audit_log.find({"action": "data.erase"})
    assert (entry["target_type"], entry["target_id"], entry["actor_user_id"]) == ("recording", target, "u-owner")
    assert "Asha" not in str(entry["meta"])  # counts and the reason, no names or content
    assert api.erase("recording", target, confirm=True).status_code == 404  # nothing left


def test_a_person_is_erased_with_every_recording_and_their_login(api: Api) -> None:
    mine = [full_recording(api, "p-asha") for _ in range(2)]
    colleague = full_recording(api, "p-ravi")

    erased = api.erase("person", "p-asha", confirm=True)
    assert erased.status_code == 200, erased.text
    assert erased.json()["recordings"] == 2
    assert all(api.documents(rid) == 0 and api.files(T, rid) == 0 for rid in mine)
    assert api.db.people.count_documents({"_id": "p-asha"}) == 0
    assert api.db.users.count_documents({"_id": "u-asha"}) == 0
    assert api.db.identities.count_documents({"user_id": "u-asha"}) == 0
    assert api.documents(colleague) == 8 and api.db.people.count_documents({"_id": "p-ravi"}) == 1
    assert api.erase("person", "p-b", confirm=True).status_code == 404  # another tenant's person
    assert api.db.people.count_documents({"_id": "p-b"}) == 1
