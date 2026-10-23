"""transition() and stage runs against MongoDB (plan task P2.3, database part). Tests written first.

The pure table is tested in test_state.py. Here: the conditional update through the tenant-scoped repository, the
outbox event it returns, consent (golden rule 9), concurrency, tenant isolation, and one stage_runs document per
attempt.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import product
from typing import Any

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording, StageRun
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo, TenantRepo
from sabha_core.stage_runs import finish_stage_run, start_stage_run
from sabha_core.state import (
    ALLOWED_TRANSITIONS,
    ConcurrentTransition,
    ConsentRequired,
    InvalidTransition,
    RecordingNotFound,
    RecordingStatus,
    transition,
    transition_async,
)

pytestmark = pytest.mark.integration

S = RecordingStatus
NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"state_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str) -> Database[dict[str, Any]]:
    database = mongo_replica_set[shared_db]
    for collection in ("recordings", "stage_runs"):
        database[collection].delete_many({})
    return database


def recordings(db: Database[dict[str, Any]], tenant_id: str = "tenant-a") -> SyncTenantRepo[Recording]:
    return SyncTenantRepo(db, "recordings", tenant_id, Recording)


def make(
    db: Database[dict[str, Any]], status: S, *, consent_ref: str | None = "consent-2026-27", tenant: str = "tenant-a"
) -> str:
    recording = Recording(type=ConversationType.TEACHING, status=status, consent_ref=consent_ref)
    return recordings(db, tenant).insert_one(recording).id


def status_of(db: Database[dict[str, Any]], recording_id: str) -> str:
    doc = db.recordings.find_one({"_id": recording_id})
    assert doc is not None
    return str(doc["status"])


# --- Every pair of statuses ---

PAIRS = [(a, b) for a, b in product(S, S) if a is not b]


@pytest.mark.parametrize(("source", "target"), PAIRS, ids=[f"{a}->{b}" for a, b in PAIRS])
def test_every_transition_is_applied_or_refused_as_the_table_says(
    db: Database[dict[str, Any]], source: S, target: S
) -> None:
    recording_id = make(db, source)
    repo = recordings(db)
    if target in ALLOWED_TRANSITIONS[source]:
        event = transition(repo, recording_id, source, target, reason="test", now=NOW)
        assert status_of(db, recording_id) == target
        assert event.type == f"recording.{target.lower()}"
        assert event.tenant_id == "tenant-a"
    else:
        with pytest.raises(InvalidTransition):
            transition(repo, recording_id, source, target, reason="test", now=NOW)
        assert status_of(db, recording_id) == source


def test_the_update_records_why_and_when(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.PREPROCESSING)
    transition(recordings(db), recording_id, S.PREPROCESSING, S.FAILED, reason="invalid_audio", now=NOW)
    doc = db.recordings.find_one({"_id": recording_id})
    assert doc is not None
    assert (doc["status"], doc["status_reason"]) == ("FAILED", "invalid_audio")
    assert doc["status_changed_at"].replace(tzinfo=UTC) == NOW


def test_the_returned_outbox_event_describes_the_change(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.CREATED)
    event = transition(
        recordings(db), recording_id, S.CREATED, S.UPLOADED, reason="upload_complete", meta={"size_bytes": 10}, now=NOW
    )
    assert event.type == "recording.uploaded"
    assert event.payload == {
        "recording_id": recording_id,
        "from_status": "CREATED",
        "to_status": "UPLOADED",
        "reason": "upload_complete",
        "meta": {"size_bytes": 10},
    }
    assert event.published_at is None and event.created_at == NOW
    assert db.outbox.count_documents({}) == 0  # returned, not written: P2.5 writes it in the same transaction


def test_reanalysis_needs_the_flag(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.COMPLETED)
    with pytest.raises(InvalidTransition):
        transition(recordings(db), recording_id, S.COMPLETED, S.ANALYZING, reason="rubric v1.1", now=NOW)
    transition(recordings(db), recording_id, S.COMPLETED, S.ANALYZING, reason="rubric v1.1", reanalysis=True, now=NOW)
    assert status_of(db, recording_id) == "ANALYZING"


def test_a_review_outcome_needs_the_flag(db: Database[dict[str, Any]]) -> None:
    confirmed = make(db, S.NEEDS_REVIEW)
    with pytest.raises(InvalidTransition):
        transition(recordings(db), confirmed, S.NEEDS_REVIEW, S.TRANSCRIBING, reason="roles_confirmed", now=NOW)
    event = transition(recordings(db), confirmed, S.NEEDS_REVIEW, S.TRANSCRIBING, reason="roles_confirmed",
                       review=True, now=NOW)  # fmt: skip
    assert (status_of(db, confirmed), event.type) == ("TRANSCRIBING", "recording.transcribing")
    closed = make(db, S.NEEDS_REVIEW)
    transition(recordings(db), closed, S.NEEDS_REVIEW, S.FAILED, reason="closed_by_reviewer", review=True, now=NOW)
    assert status_of(db, closed) == "FAILED"


# --- Consent first (golden rule 9) ---


@pytest.mark.parametrize("consent_ref", [None, ""])
def test_without_consent_nothing_moves_past_uploaded(db: Database[dict[str, Any]], consent_ref: str | None) -> None:
    recording_id = make(db, S.UPLOADED, consent_ref=consent_ref)
    with pytest.raises(ConsentRequired):
        transition(recordings(db), recording_id, S.UPLOADED, S.PREPROCESSING, reason="queued", now=NOW)
    assert status_of(db, recording_id) == "UPLOADED"


def test_an_upload_may_complete_before_consent_is_recorded(db: Database[dict[str, Any]]) -> None:
    # P2.2: without consent the recording stays UPLOADED (awaiting_consent) and is not queued.
    recording_id = make(db, S.CREATED, consent_ref=None)
    transition(recordings(db), recording_id, S.CREATED, S.UPLOADED, reason="upload_complete", now=NOW)
    assert status_of(db, recording_id) == "UPLOADED"


# --- Concurrency and isolation ---


def test_a_stale_from_status_loses_cleanly(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.UPLOADED)
    transition(recordings(db), recording_id, S.UPLOADED, S.PREPROCESSING, reason="first", now=NOW)
    with pytest.raises(ConcurrentTransition):
        transition(recordings(db), recording_id, S.UPLOADED, S.PREPROCESSING, reason="second", now=NOW)
    doc = db.recordings.find_one({"_id": recording_id})
    assert doc is not None and doc["status_reason"] == "first"


def test_only_one_of_many_racing_workers_wins(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.UPLOADED)
    outcomes: list[str] = []
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        barrier.wait()
        try:
            transition(recordings(db), recording_id, S.UPLOADED, S.PREPROCESSING, reason=f"w{n}", now=NOW)
            outcomes.append("won")
        except ConcurrentTransition:
            outcomes.append("lost")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["lost"] * 7 + ["won"]


def test_another_tenants_recording_is_not_found(db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.UPLOADED, tenant="tenant-b")
    with pytest.raises(RecordingNotFound):
        transition(recordings(db, "tenant-a"), recording_id, S.UPLOADED, S.PREPROCESSING, reason="x", now=NOW)
    assert status_of(db, recording_id) == "UPLOADED"


def test_an_unknown_recording_is_not_found(db: Database[dict[str, Any]]) -> None:
    with pytest.raises(RecordingNotFound):
        transition(recordings(db), "missing", S.UPLOADED, S.PREPROCESSING, reason="x", now=NOW)


# --- Async (API) variant, inside a transaction ---


def test_async_transition_rolls_back_with_its_transaction(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    recording_id = make(db, S.CREATED)

    async def scenario() -> None:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri, tz_aware=True)
        repo = TenantRepo(client[db.name], "recordings", "tenant-a", Recording)
        try:
            async with client.start_session() as session:
                with pytest.raises(RuntimeError):
                    async with await session.start_transaction():
                        await transition_async(
                            repo, recording_id, S.CREATED, S.UPLOADED, reason="x", now=NOW, session=session
                        )
                        raise RuntimeError("abort")
            assert status_of(db, recording_id) == "CREATED"
            event = await transition_async(repo, recording_id, S.CREATED, S.UPLOADED, reason="x", now=NOW)
            assert event.type == "recording.uploaded"
        finally:
            await client.close()

    asyncio.run(scenario())
    assert status_of(db, recording_id) == "UPLOADED"


# --- Stage runs: one document per attempt ---


def runs(db: Database[dict[str, Any]], tenant_id: str = "tenant-a") -> SyncTenantRepo[StageRun]:
    return SyncTenantRepo(db, "stage_runs", tenant_id, StageRun)


def test_each_attempt_gets_its_own_stage_run(db: Database[dict[str, Any]]) -> None:
    first = start_stage_run(runs(db), "rec-1", "preprocess", "v1", worker="cpu-1", now=NOW)
    second = start_stage_run(runs(db), "rec-1", "preprocess", "v1", worker="cpu-2", now=NOW)
    other_stage = start_stage_run(runs(db), "rec-1", "diarize", "v1", worker="gpu-1", now=NOW)
    other_version = start_stage_run(runs(db), "rec-1", "preprocess", "v2", worker="cpu-1", now=NOW)
    assert (first.attempt, second.attempt, other_stage.attempt, other_version.attempt) == (1, 2, 1, 1)
    assert first.status == "running" and first.started_at == NOW and first.finished_at is None
    assert db.stage_runs.count_documents({"recording_id": "rec-1"}) == 4


def test_finishing_a_run_records_the_outcome_and_duration(db: Database[dict[str, Any]]) -> None:
    run = start_stage_run(runs(db), "rec-1", "preprocess", "v1", worker="cpu-1", now=NOW)
    later = NOW + timedelta(seconds=42, milliseconds=500)
    done = finish_stage_run(runs(db), run, succeeded=True, meta={"audio_s": 3600}, now=later)
    assert (done.status, done.finished_at, done.duration_ms, done.meta) == (
        "succeeded",
        later,
        42_500,
        {"audio_s": 3600},
    )
    stored = db.stage_runs.find_one({"_id": run.id})
    assert stored is not None and stored["status"] == "succeeded" and stored["duration_ms"] == 42_500


def test_a_failed_run_keeps_its_error_code_and_a_bounded_detail(db: Database[dict[str, Any]]) -> None:
    run = start_stage_run(runs(db), "rec-1", "preprocess", "v1", worker="cpu-1", now=NOW)
    done = finish_stage_run(
        runs(db), run, succeeded=False, error_code="invalid_audio", error_detail="x" * 10_000, now=NOW
    )
    assert (done.status, done.error_code) == ("failed", "invalid_audio")
    assert done.error_detail is not None and len(done.error_detail) <= 2000


def test_racing_starts_get_distinct_attempt_numbers(db: Database[dict[str, Any]]) -> None:
    attempts: list[int] = []
    barrier = threading.Barrier(6)

    def worker() -> None:
        barrier.wait()
        attempts.append(start_stage_run(runs(db), "rec-race", "preprocess", "v1", worker="w", now=NOW).attempt)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(attempts) == [1, 2, 3, 4, 5, 6]


def test_stage_runs_are_counted_per_tenant(db: Database[dict[str, Any]]) -> None:
    start_stage_run(runs(db, "tenant-b"), "rec-1", "preprocess", "v1", worker="w", now=NOW)
    assert start_stage_run(runs(db, "tenant-a"), "rec-1", "preprocess", "v1", worker="w", now=NOW).attempt == 1
