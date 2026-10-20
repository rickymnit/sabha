"""The transactional outbox (plan task P2.5): a status change and its event are written together or not at all."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import OutboxEvent, Recording
from sabha_core.outbox import record_event_async, record_transition, record_transition_async
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo, TenantRepo
from sabha_core.state import ConcurrentTransition, RecordingStatus

pytestmark = pytest.mark.integration
S = RecordingStatus


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"outbox_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def repos(db: Database[dict[str, Any]]) -> tuple[SyncTenantRepo[Recording], SyncTenantRepo[OutboxEvent]]:
    return SyncTenantRepo(db, "recordings", "t1", Recording), SyncTenantRepo(db, "outbox", "t1", OutboxEvent)


def status_of(db: Database[dict[str, Any]], recording_id: str) -> str:
    doc = db.recordings.find_one({"_id": recording_id})
    assert doc is not None
    return str(doc["status"])


def make(db: Database[dict[str, Any]], status: S) -> str:
    recordings, _ = repos(db)
    return recordings.insert_one(Recording(type=ConversationType.TEACHING, status=status, consent_ref="c")).id


def test_the_change_and_its_event_commit_together(
    mongo_replica_set: MongoClient[dict[str, Any]], db: Database[dict[str, Any]]
) -> None:
    rid = make(db, S.PREPROCESSING)
    recordings, outbox = repos(db)
    with mongo_replica_set.start_session() as session, session.start_transaction():
        event = record_transition(
            recordings, outbox, rid, S.PREPROCESSING, S.DIARIZING, session=session, reason="preprocessed"
        )
    assert status_of(db, rid) == "DIARIZING"
    stored = db.outbox.find_one({"_id": event.id})
    assert stored is not None
    assert (stored["tenant_id"], stored["type"], stored["published_at"]) == ("t1", "recording.diarizing", None)
    assert stored["payload"]["recording_id"] == rid


def test_a_rolled_back_transaction_leaves_no_event(
    mongo_replica_set: MongoClient[dict[str, Any]], db: Database[dict[str, Any]]
) -> None:
    rid = make(db, S.PREPROCESSING)
    recordings, outbox = repos(db)
    with mongo_replica_set.start_session() as session, pytest.raises(RuntimeError), session.start_transaction():
        record_transition(recordings, outbox, rid, S.PREPROCESSING, S.DIARIZING, session=session, reason="x")
        raise RuntimeError("abort")
    assert db.outbox.count_documents({}) == 0
    assert status_of(db, rid) == "PREPROCESSING"


def test_a_refused_transition_writes_no_event(
    mongo_replica_set: MongoClient[dict[str, Any]], db: Database[dict[str, Any]]
) -> None:
    rid = make(db, S.DIARIZING)
    recordings, outbox = repos(db)
    with (
        mongo_replica_set.start_session() as session,
        session.start_transaction(),
        pytest.raises(ConcurrentTransition),
    ):
        record_transition(recordings, outbox, rid, S.PREPROCESSING, S.DIARIZING, session=session, reason="x")
    assert db.outbox.count_documents({}) == 0


def test_async_helpers(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    rid = make(db, S.CREATED)

    async def scenario() -> None:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        recordings = TenantRepo(client[db.name], "recordings", "t1", Recording)
        outbox = TenantRepo(client[db.name], "outbox", "t1", OutboxEvent)
        try:
            async with client.start_session() as session, await session.start_transaction():
                await record_transition_async(
                    recordings, outbox, rid, S.CREATED, S.UPLOADED, session=session, reason="upload_complete"
                )
                await record_event_async(outbox, "recording.ready", {"recording_id": rid}, session=session)
        finally:
            await client.close()

    asyncio.run(scenario())
    assert sorted(d["type"] for d in db.outbox.find()) == ["recording.ready", "recording.uploaded"]
