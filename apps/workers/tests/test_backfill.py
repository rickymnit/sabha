"""scripts/admin/backfill.py (sabha_workers.backfill): fills strips, speech time and tickets from storage, once."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Analysis, Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.state import RecordingStatus
from sabha_core.timemap import build_segment_map
from sabha_workers.backfill import backfill

pytestmark = pytest.mark.integration
T = "t-backfill"
BUCKET = "sabha-artefacts"


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"fill_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def insert(db: Database[dict[str, Any]], collection: str, doc: Any) -> None:
    db[collection].insert_one(doc.model_dump(by_alias=True))


def one(db: Database[dict[str, Any]], collection: str, query: dict[str, Any]) -> dict[str, Any]:
    found = db[collection].find_one(query)
    assert found is not None
    return found


def test_backfill_fills_what_is_missing_once_and_skips_missing_files(
    db: Database[dict[str, Any]], s3_storage: Any
) -> None:
    s3 = s3_storage.client()
    insert(db, "tenants", Tenant.from_profile("school", name="Sunrise", plan=Plan.PILOT, id=T))
    for rid, kind in (("r-lesson", ConversationType.TEACHING), ("r-call", ConversationType.RECEPTION),
                      ("r-lost", ConversationType.TEACHING)):  # fmt: skip
        insert(db, "recordings", Recording(id=rid, tenant_id=T, type=kind, status=RecordingStatus.COMPLETED,
                                           consent_ref="c", duration_ms=60_000))  # fmt: skip
    segments = build_segment_map([(0, 20_000), (40_000, 50_000)], 60_000, 0, 0)
    s3.put_object(Bucket=BUCKET, Key=f"{T}/r-lesson/preprocess@v1/segments@v1.json", Body=segments.to_json().encode())
    utterances = [{"role": "teacher", "start_ms": 0, "end_ms": 20_000}, {"role": "students", "start_ms": 40_000,
                                                                          "end_ms": 50_000}]  # fmt: skip
    s3.put_object(Bucket=BUCKET, Key=f"{T}/r-lesson/t.json", Body=json.dumps({"utterances": utterances}).encode())
    insert(db, "transcripts", Transcript(
        tenant_id=T, recording_id="r-lesson", version="transcript@v1", storage_key=f"{T}/r-lesson/t.json",
        asr_model="m", word_timing="approximate", word_count=2, utterance_count=2,
        role_choices=["teacher", "students"], rubric_id="teaching.school.v0.1",
    ))  # fmt: skip
    ticket = {"status": "resolved", "category": "fee_query", "follow_up": None,
              "evidence": {"need": {"quote": "q"}, "outcome": {"quote": "q"}}}  # fmt: skip
    s3.put_object(Bucket=BUCKET, Key=f"{T}/r-call/a.json", Body=json.dumps({"ticket": ticket}).encode())
    insert(db, "analyses", Analysis(
        tenant_id=T, recording_id="r-call", version="v1", conversation_type=ConversationType.RECEPTION,
        rubric_id="reception.school.v0.2", rubric_version="0.2", rubric_hash="h", report_key=f"{T}/r-call/a.json",
        status="COMPLETED", verified_share=1.0,
    ))  # fmt: skip

    dry = backfill(db, s3, artefacts_bucket=BUCKET, preprocess_version="v1", dry_run=True)
    assert one(db, "transcripts", {"recording_id": "r-lesson"})["speaker_strip"] == []  # a dry run writes nothing
    (done,) = backfill(db, s3, artefacts_bucket=BUCKET, preprocess_version="v1")
    assert dry == [done]
    # r-call and r-lost have no segments file: counted as missing and skipped, not guessed
    assert (done.strips, done.speech, done.tickets, done.missing_files) == (1, 1, 1, 2)
    strip = one(db, "transcripts", {"recording_id": "r-lesson"})["speaker_strip"]
    assert [(s["start_ms"], s["speaker"]) for s in strip] == [(0, "staff"), (40_000, "other")]
    assert one(db, "recordings", {"_id": "r-lesson"})["speech_ms"] == 30_000
    assert one(db, "analyses", {"recording_id": "r-call"})["ticket_status"] == "resolved"

    (again,) = backfill(db, s3, artefacts_bucket=BUCKET, preprocess_version="v1")
    assert (again.strips, again.speech, again.tickets) == (0, 0, 0)  # nothing left; only the missing files remain
