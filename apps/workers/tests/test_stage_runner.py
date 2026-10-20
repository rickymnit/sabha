"""StageRunner (plan task P2.4) against MongoDB and RustFS: entry, idempotent skip, retries, dead letters, review."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo
from sabha_core.state import RecordingStatus
from sabha_workers.stages.runner import (
    DONE_MARKER,
    NeedsReviewError,
    PermanentError,
    S3Artefacts,
    StageContext,
    StageRunner,
    StageSpec,
    TransientError,
)

pytestmark = pytest.mark.integration
S = RecordingStatus
PREPROCESS = StageSpec("preprocess", working=S.PREPROCESSING, done_to=S.DIARIZING, entry_from=S.UPLOADED)
DIARIZE = StageSpec("diarize", working=S.DIARIZING, done_to=S.TRANSCRIBING)
VERSIONS = {"preprocess": "v1", "diarize": "v1"}


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"stage_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs", "outbox", "dlq"):
        database[collection].delete_many({})
    return database


@pytest.fixture
def artefacts(s3_storage: Any) -> S3Artefacts:
    return S3Artefacts(s3_storage.client(), "sabha-artefacts")


def runner(db: Database[dict[str, Any]], artefacts: S3Artefacts, max_attempts: int = 3) -> StageRunner:
    return StageRunner(db=db, artefacts=artefacts, versions=VERSIONS, worker="test-worker",
                       max_attempts=max_attempts, jitter=lambda: 1.0)  # fmt: skip


def make(db: Database[dict[str, Any]], status: S, tenant: str = "t1") -> str:
    recording = Recording(type=ConversationType.TEACHING, status=status, consent_ref="c")
    return SyncTenantRepo(db, "recordings", tenant, Recording).insert_one(recording).id


def status_of(db: Database[dict[str, Any]], rid: str) -> str:
    doc = db.recordings.find_one({"_id": rid})
    assert doc is not None
    return str(doc["status"])


def event_types(db: Database[dict[str, Any]], rid: str) -> list[str]:
    return [e["type"] for e in db.outbox.find({"payload.recording_id": rid}).sort("created_at", 1)]


class Work:
    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def __call__(self, ctx: StageContext) -> dict[str, Any]:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        ctx.artefacts.put(ctx.prefix + "normalised.wav", b"RIFF")
        return {"audio_s": 3600}


# --- The happy path ---


def test_a_stage_enters_works_marks_done_and_moves_on(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    work = Work()
    assert runner(db, artefacts).run(PREPROCESS, work, "t1", rid, attempt=1).result == "done"
    assert status_of(db, rid) == "DIARIZING"
    assert event_types(db, rid) == ["recording.preprocessing", "recording.diarizing"]  # the relay starts diarize
    assert artefacts.exists(f"t1/{rid}/preprocess@v1/{DONE_MARKER}")
    (run,) = db.stage_runs.find({"recording_id": rid})
    assert (run["status"], run["attempt"], run["meta"]) == ("succeeded", 1, {"audio_s": 3600})


def test_a_stage_without_an_entry_step_works_from_its_status(
    db: Database[dict[str, Any]], artefacts: S3Artefacts
) -> None:
    rid = make(db, S.DIARIZING)
    assert runner(db, artefacts).run(DIARIZE, Work(), "t1", rid, attempt=1).result == "done"
    assert status_of(db, rid) == "TRANSCRIBING"


# --- Idempotency (golden rule 3) ---


def test_finished_work_is_never_redone(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.PREPROCESSING)  # a worker died after writing _DONE, before moving the status on
    artefacts.put(f"t1/{rid}/preprocess@v1/{DONE_MARKER}", b"")
    work = Work()
    assert runner(db, artefacts).run(PREPROCESS, work, "t1", rid, attempt=2).result == "work_skipped"
    assert work.calls == 0 and status_of(db, rid) == "DIARIZING"


def test_a_redelivered_task_resumes_an_interrupted_stage(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    first = runner(db, artefacts)
    first._move("t1", rid, S.UPLOADED, S.PREPROCESSING, "preprocess_started")  # then the worker was killed
    assert runner(db, artefacts).run(PREPROCESS, Work(), "t1", rid, attempt=1).result == "done"
    assert event_types(db, rid) == ["recording.preprocessing", "recording.diarizing"]  # no second "started" event


def test_a_recording_past_the_stage_is_left_alone(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.TRANSCRIBING)
    work = Work()
    assert runner(db, artefacts).run(PREPROCESS, work, "t1", rid, attempt=1).result == "already_done"
    assert work.calls == 0 and status_of(db, rid) == "TRANSCRIBING"


@pytest.mark.parametrize("status", [S.FAILED, S.NEEDS_REVIEW])
def test_stopped_recordings_are_not_processed(db: Database[dict[str, Any]], artefacts: S3Artefacts, status: S) -> None:
    rid = make(db, status)
    assert runner(db, artefacts).run(PREPROCESS, Work(), "t1", rid, attempt=1).result == "stopped"


def test_another_tenants_recording_is_not_found(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED, tenant="t2")
    assert runner(db, artefacts).run(PREPROCESS, Work(), "t1", rid, attempt=1).result == "missing"
    assert status_of(db, rid) == "UPLOADED"


# --- Retries, dead letters, review ---


def test_transient_errors_ask_for_a_retry_with_backoff(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    r = runner(db, artefacts)
    first = r.run(PREPROCESS, Work(TransientError("provider_timeout")), "t1", rid, attempt=1)
    second = r.run(PREPROCESS, Work(TransientError("provider_timeout")), "t1", rid, attempt=2)
    assert (first.result, first.retry_in, second.retry_in) == ("retry", 10.0, 20.0)
    assert status_of(db, rid) == "PREPROCESSING"
    assert [run["status"] for run in db.stage_runs.find({"recording_id": rid}).sort("attempt", 1)] == [
        "failed",
        "failed",
    ]
    assert r.run(PREPROCESS, Work(), "t1", rid, attempt=3).result == "done"


def test_retries_run_out_into_failed_and_a_dead_letter(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    outcome = runner(db, artefacts, max_attempts=3).run(
        PREPROCESS, Work(TransientError("provider_timeout", "after 60 s")), "t1", rid, attempt=3
    )
    assert outcome.result == "failed" and status_of(db, rid) == "FAILED"
    (letter,) = db.dlq.find({"recording_id": rid})
    assert (letter["tenant_id"], letter["stage"], letter["error_code"], letter["attempts"]) == (
        "t1", "preprocess", "provider_timeout", 3,
    )  # fmt: skip
    assert letter["args"] == {"tenant_id": "t1", "recording_id": rid}
    assert event_types(db, rid)[-1] == "recording.failed"  # the relay notifies admins


def test_unexpected_errors_are_retried_like_transient_ones(
    db: Database[dict[str, Any]], artefacts: S3Artefacts
) -> None:
    rid = make(db, S.UPLOADED)
    outcome = runner(db, artefacts).run(PREPROCESS, Work(KeyError("bug")), "t1", rid, attempt=1)
    assert outcome.result == "retry"
    (run,) = db.stage_runs.find({"recording_id": rid})
    assert run["error_code"] == "unexpected_KeyError"


def test_permanent_errors_fail_at_once(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    outcome = runner(db, artefacts).run(
        PREPROCESS, Work(PermanentError("invalid_audio", "corrupt")), "t1", rid, attempt=1
    )
    assert outcome.result == "failed" and status_of(db, rid) == "FAILED"
    (letter,) = db.dlq.find({"recording_id": rid})
    assert (letter["error_code"], letter["error_detail"], letter["attempts"]) == ("invalid_audio", "corrupt", 1)


def test_needs_review_stops_without_a_dead_letter(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.DIARIZING)
    outcome = runner(db, artefacts).run(DIARIZE, Work(NeedsReviewError("unclear_roles")), "t1", rid, attempt=1)
    assert outcome.result == "needs_review" and status_of(db, rid) == "NEEDS_REVIEW"
    assert db.dlq.count_documents({}) == 0
    doc = db.recordings.find_one({"_id": rid})
    assert doc is not None and doc["status_reason"] == "unclear_roles"


def test_work_that_fails_writes_no_done_marker(db: Database[dict[str, Any]], artefacts: S3Artefacts) -> None:
    rid = make(db, S.UPLOADED)
    runner(db, artefacts).run(PREPROCESS, Work(TransientError("x")), "t1", rid, attempt=1)
    assert not artefacts.exists(f"t1/{rid}/preprocess@v1/{DONE_MARKER}")
