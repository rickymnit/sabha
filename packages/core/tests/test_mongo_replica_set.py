"""The MongoDB that development and tests use must be a replica set with working transactions (CLAUDE.md)."""

from __future__ import annotations

from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure

pytestmark = pytest.mark.integration


def test_server_is_a_replica_set_primary(mongo_replica_set: MongoClient[dict[str, Any]]) -> None:
    hello = mongo_replica_set.admin.command("hello")

    assert hello["setName"] == "rs0"
    assert hello["isWritablePrimary"] is True


def test_transaction_commits_all_writes(mongo_replica_set: MongoClient[dict[str, Any]]) -> None:
    db = mongo_replica_set["txn_commit"]
    db.drop_collection("recordings")
    db.drop_collection("outbox")
    db.create_collection("recordings")
    db.create_collection("outbox")

    with mongo_replica_set.start_session() as session, session.start_transaction():
        db.recordings.insert_one({"_id": "r1", "tenant_id": "t1", "status": "UPLOADED"}, session=session)
        db.outbox.insert_one({"tenant_id": "t1", "type": "recording.uploaded", "recording_id": "r1"}, session=session)

    assert db.recordings.count_documents({"_id": "r1"}) == 1
    assert db.outbox.count_documents({"recording_id": "r1"}) == 1


def test_aborted_transaction_leaves_nothing(mongo_replica_set: MongoClient[dict[str, Any]]) -> None:
    # The outbox pattern (P2.5) relies on this: a status change and its event are written together or not at all.
    db = mongo_replica_set["txn_abort"]
    db.drop_collection("recordings")
    db.drop_collection("outbox")
    db.create_collection("recordings")
    db.create_collection("outbox")

    with mongo_replica_set.start_session() as session:
        session.start_transaction()
        db.recordings.insert_one({"_id": "r1", "tenant_id": "t1", "status": "UPLOADED"}, session=session)
        db.outbox.insert_one({"tenant_id": "t1", "type": "recording.uploaded", "recording_id": "r1"}, session=session)
        session.abort_transaction()

    assert db.recordings.count_documents({}) == 0
    assert db.outbox.count_documents({}) == 0


def test_change_stream_opens(mongo_replica_set: MongoClient[dict[str, Any]]) -> None:
    # Change streams (the outbox relay, P2.5) are refused by a standalone server; a replica set accepts them.
    db = mongo_replica_set["change_stream"]
    try:
        with db.outbox.watch(max_await_time_ms=100) as stream:
            assert stream.try_next() is None
    except OperationFailure as exc:  # pragma: no cover - only on a misconfigured server
        pytest.fail(f"change streams unavailable: {exc}")
