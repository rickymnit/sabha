"""Audio retention (P7.3): only expired audio is deleted, for the right tenant; transcripts and reports stay."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording, Tenant, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.state import RecordingStatus
from sabha_workers.retention import expire_audio

pytestmark = pytest.mark.integration
AUDIO, ARTEFACTS = "sabha-audio", "sabha-artefacts"
NOW = utc_now()


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"retention_{uuid.uuid4().hex[:12]}"
    database = mongo_replica_set[name]
    ensure_indexes(database)
    for tenant_id, days in (("t-90", 90), ("t-365", 365)):
        tenant = Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id, retention_days=days)
        database.tenants.insert_one(tenant.model_dump(by_alias=True))
    yield database
    mongo_replica_set.drop_database(name)


def stored(db: Database[dict[str, Any]], s3: Any, tenant: str, *, days_old: int,
           status: RecordingStatus = RecordingStatus.COMPLETED) -> str:  # fmt: skip
    """A recording with an original, audio working copies and JSON outputs in storage."""
    rid = f"r{uuid.uuid4().hex[:10]}"
    recording = Recording(id=rid, tenant_id=tenant, type=ConversationType.TEACHING, status=status, consent_ref="c",
                          created_at=NOW - timedelta(days=days_old))  # fmt: skip
    db.recordings.insert_one(recording.model_dump(by_alias=True))
    s3.put_object(Bucket=AUDIO, Key=f"{tenant}/{rid}/original/lesson.mp3", Body=b"a")
    for name in (
        "preprocess@v2/normalised.wav",
        "preprocess@v2/playback.opus",
        "preprocess@v2/compact.wav",
        "preprocess@v2/segments@v1.json",
        "transcribe@v1/transcript@v1.json",
        "analyze@v1/analysis@v1.json",
    ):
        s3.put_object(Bucket=ARTEFACTS, Key=f"{tenant}/{rid}/{name}", Body=b"x")
    return rid


def keys(s3: Any, bucket: str, prefix: str) -> set[str]:
    page = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return {obj["Key"].removeprefix(prefix) for obj in page.get("Contents", [])}


def test_only_expired_audio_goes_and_the_rest_stays(db: Database[dict[str, Any]], s3_storage: Any) -> None:
    s3 = s3_storage.client()
    expired = stored(db, s3, "t-90", days_old=91)
    fresh = stored(db, s3, "t-90", days_old=89)
    running = stored(db, s3, "t-90", days_old=200, status=RecordingStatus.TRANSCRIBING)
    longer = stored(db, s3, "t-365", days_old=200)  # another tenant keeps audio for a year

    done = expire_audio(db, s3, audio_bucket=AUDIO, artefacts_bucket=ARTEFACTS, now=NOW)

    assert [(d.tenant_id, d.recordings, d.objects) for d in done] == [("t-90", 1, 4)]
    assert keys(s3, AUDIO, f"t-90/{expired}/") == set()
    assert keys(s3, ARTEFACTS, f"t-90/{expired}/") == {
        "preprocess@v2/segments@v1.json", "transcribe@v1/transcript@v1.json", "analyze@v1/analysis@v1.json",
    }  # fmt: skip
    assert db.recordings.find_one({"_id": expired})["audio_deleted_at"] is not None  # type: ignore[index]
    for tenant, rid in (("t-90", fresh), ("t-90", running), ("t-365", longer)):
        assert len(keys(s3, ARTEFACTS, f"{tenant}/{rid}/")) == 6 and keys(s3, AUDIO, f"{tenant}/{rid}/")
        assert db.recordings.find_one({"_id": rid})["audio_deleted_at"] is None  # type: ignore[index]
    [entry] = db.audit_log.find({"action": "audio.expire"})
    assert (entry["tenant_id"], entry["meta"]["recording_ids"]) == ("t-90", [expired])
    # Running again finds nothing new.
    assert expire_audio(db, s3, audio_bucket=AUDIO, artefacts_bucket=ARTEFACTS, now=NOW) == []


def test_a_dry_run_deletes_nothing(db: Database[dict[str, Any]], s3_storage: Any) -> None:
    s3 = s3_storage.client()
    rid = stored(db, s3, "t-90", days_old=120)
    [done] = expire_audio(db, s3, audio_bucket=AUDIO, artefacts_bucket=ARTEFACTS, now=NOW, dry_run=True)
    assert (done.recordings, done.objects) == (1, 4)
    assert len(keys(s3, ARTEFACTS, f"t-90/{rid}/")) == 6 and keys(s3, AUDIO, f"t-90/{rid}/")
    assert db.recordings.find_one({"_id": rid})["audio_deleted_at"] is None  # type: ignore[index]
    assert db.audit_log.count_documents({}) == 0
