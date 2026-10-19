"""The outbox relay (plan task P2.5) against a real MongoDB replica set: routing, no duplicate dispatch, the
fallback sweep, and resuming the change stream after a restart.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database
from redis.exceptions import ConnectionError as RedisConnectionError

from sabha_core.indexes import ensure_indexes
from sabha_core.models import OutboxEvent, RelayState, utc_now
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_workers.relay import Relay, live_message, routes

pytestmark = pytest.mark.integration


class FakeDispatcher:
    def __init__(self, fail_on: str | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail_on = fail_on

    def send(self, task: str, event: OutboxEvent) -> None:
        if task == self.fail_on:
            raise RuntimeError("broker down")
        self.sent.append((task, event.payload["recording_id"]))


class FakePublisher:
    def __init__(self, broken: bool = False) -> None:
        self.messages: list[tuple[str, str]] = []
        self.broken = broken

    def publish(self, channel: str, message: str) -> None:
        if self.broken:
            raise RedisConnectionError("redis down")
        self.messages.append((channel, message))


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"relay_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def relay(db: Database[dict[str, Any]], dispatcher: FakeDispatcher, publisher: FakePublisher | None = None) -> Relay:
    return Relay(
        SyncSystemRepo(db, "outbox", OutboxEvent),
        SyncSystemRepo(db, "relay_state", RelayState),
        dispatcher,
        publisher or FakePublisher(),
    )


def emit(
    db: Database[dict[str, Any]], event_type: str, recording_id: str = "r1", tenant: str = "t1", **meta: Any
) -> str:
    event = OutboxEvent(type=event_type, payload={"recording_id": recording_id, "meta": meta})
    return SyncTenantRepo(db, "outbox", tenant, OutboxEvent).insert_one(event).id


def wait_for(condition: Callable[[], bool], timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


# --- Routing ---


@pytest.mark.parametrize(
    ("event_type", "meta", "tasks"),
    [
        ("recording.uploaded", {"ready": True}, ("preprocess",)),
        ("recording.uploaded", {"ready": False}, ()),
        ("recording.uploaded", {}, ()),
        ("recording.ready", {}, ("preprocess",)),
        ("recording.preprocessing", {}, ()),
        ("recording.diarizing", {}, ("diarize",)),
        ("recording.transcribing", {}, ("transcribe",)),
        ("recording.analyzing", {}, ("analyze",)),
        ("recording.completed", {}, ("notify", "meter")),
        ("recording.failed", {}, ("notify",)),
        ("recording.needs_review", {}, ("notify",)),
    ],
)
def test_routing_table(event_type: str, meta: dict[str, Any], tasks: tuple[str, ...]) -> None:
    assert routes(OutboxEvent(tenant_id="t1", type=event_type, payload={"meta": meta})) == tasks


# --- Handling ---


def test_an_event_is_dispatched_published_and_marked(db: Database[dict[str, Any]]) -> None:
    dispatcher, publisher = FakeDispatcher(), FakePublisher()
    event_id = emit(db, "recording.completed")
    assert relay(db, dispatcher, publisher).handle(event_id) is True
    assert dispatcher.sent == [("notify", "r1"), ("meter", "r1")]
    assert [channel for channel, _ in publisher.messages] == ["events:t1"]
    stored = db.outbox.find_one({"_id": event_id})
    assert stored is not None and stored["published_at"] is not None and stored["dispatched"] == ["notify", "meter"]


def test_handling_twice_never_dispatches_twice(db: Database[dict[str, Any]]) -> None:
    dispatcher = FakeDispatcher()
    event_id = emit(db, "recording.ready")
    r = relay(db, dispatcher)
    assert r.handle(event_id) is True
    assert r.handle(event_id) is False
    assert dispatcher.sent == [("preprocess", "r1")]


def test_a_partly_dispatched_event_sends_only_the_rest(db: Database[dict[str, Any]]) -> None:
    dispatcher = FakeDispatcher(fail_on="meter")
    event_id = emit(db, "recording.completed")
    with pytest.raises(RuntimeError):
        relay(db, dispatcher).handle(event_id)
    stored = db.outbox.find_one({"_id": event_id})
    assert stored is not None and stored["dispatched"] == ["notify"] and stored["published_at"] is None

    retry = FakeDispatcher()
    relay(db, retry).handle(event_id)
    assert retry.sent == [("meter", "r1")]


def test_a_held_upload_is_published_but_not_processed(db: Database[dict[str, Any]]) -> None:
    dispatcher, publisher = FakeDispatcher(), FakePublisher()
    relay(db, dispatcher, publisher).handle(emit(db, "recording.uploaded", ready=False))
    assert dispatcher.sent == [] and len(publisher.messages) == 1


def test_a_failed_live_update_does_not_block_the_pipeline(db: Database[dict[str, Any]]) -> None:
    dispatcher = FakeDispatcher()
    event_id = emit(db, "recording.diarizing")
    assert relay(db, dispatcher, FakePublisher(broken=True)).handle(event_id) is True
    assert dispatcher.sent == [("diarize", "r1")]


def test_live_messages_carry_the_event(db: Database[dict[str, Any]]) -> None:
    event = OutboxEvent(tenant_id="t1", type="recording.completed", payload={"recording_id": "r1"})
    assert '"type": "recording.completed"' in live_message(event) and '"tenant_id": "t1"' in live_message(event)


# --- Sweep ---


def test_the_sweep_handles_only_old_unpublished_events(db: Database[dict[str, Any]]) -> None:
    dispatcher = FakeDispatcher()
    old = emit(db, "recording.ready", recording_id="old")
    db.outbox.update_one({"_id": old}, {"$set": {"created_at": utc_now() - timedelta(minutes=5)}})
    emit(db, "recording.ready", recording_id="new")
    assert relay(db, dispatcher).sweep() == 1
    assert dispatcher.sent == [("preprocess", "old")]


# --- The change stream, and resuming after a restart ---


def run_in_thread(r: Relay) -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(target=r.run, args=(stop,), kwargs={"sweep_every_s": 3600}, daemon=True)
    thread.start()
    return thread, stop


def test_new_events_are_relayed_as_they_arrive_and_after_a_restart(db: Database[dict[str, Any]]) -> None:
    dispatcher = FakeDispatcher()
    thread, stop = run_in_thread(relay(db, dispatcher))
    time.sleep(1.0)  # let the stream open before the first insert
    emit(db, "recording.ready", recording_id="first")
    wait_for(lambda: dispatcher.sent == [("preprocess", "first")])
    stop.set()
    thread.join(timeout=10)

    emit(db, "recording.ready", recording_id="while-stopped")  # the relay is down
    restarted = FakeDispatcher()
    thread, stop = run_in_thread(relay(db, restarted))
    wait_for(lambda: restarted.sent == [("preprocess", "while-stopped")])
    time.sleep(1.0)  # nothing else arrives: "first" is not sent again
    stop.set()
    thread.join(timeout=10)
    assert restarted.sent == [("preprocess", "while-stopped")]
    assert db.relay_state.count_documents({"_id": "outbox"}) == 1
