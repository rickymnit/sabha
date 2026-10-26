"""Live status over server-sent events (P2.6): GET /v1/events.

- Each caller receives only events about recordings they may see (the recordings list's rules: owners and admins
  all, managers and reviewers their units, staff their own), and never another tenant's.
- Each message carries only what the page needs (type, recording, status, reason code, time), never notes.
- A comment is sent once subscribed, and a heartbeat comment while nothing happens.
- Last-Event-ID replays what was published after that event, within the last 5 minutes, from the outbox.
- Without Redis the route answers 503 live_unavailable, and the web app keeps polling.

The stream is read from a real server (uvicorn in a thread): the test client buffers a streamed response whole.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
import redis
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from sabha_api.main import create_app
from sabha_api.resources import open_resources
from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, OutboxEvent, Person, Recording, Role, Tenant, Unit, User, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import COLLECTIONS
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration
T, OTHER = "tenant-a", "tenant-b"
USERS = {  # subject -> (tenant, user id, role, units)
    "owner": (T, "u-owner", Role.OWNER, []),
    "manager": (T, "u-manager", Role.MANAGER, ["unit-1"]),
    "asha": (T, "u-asha", Role.STAFF, ["unit-1"]),
    "stranger": (OTHER, "u-stranger", Role.OWNER, []),
}


class LiveServer:
    """The app on a free local port, served by uvicorn in a thread."""

    def __init__(self, app: FastAPI) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.app = app
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 20
        while not self.server.started:
            assert time.monotonic() < deadline, "the test server did not start"
            time.sleep(0.05)

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)


@dataclass
class Api:
    client: LiveServer
    db: Database[dict[str, Any]]
    idp: Any
    redis: redis.Redis

    def listen(self, sub: str | None, *, last_event_id: str | None = None) -> Listener:
        headers = {} if sub is None else {"Authorization": f"Bearer {self.idp.token(sub)}"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        return Listener(self.client, headers)

    def publish(self, tenant_id: str, event: OutboxEvent) -> None:
        message = {"id": event.id, "type": event.type, "tenant_id": tenant_id, "payload": event.payload,
                   "created_at": event.created_at.isoformat()}  # fmt: skip
        self.redis.publish(f"events:{tenant_id}", json.dumps(message))


class Listener:
    """Reads GET /v1/events in a thread until the server ends the stream (events_max_connection_s)."""

    def __init__(self, client: LiveServer, headers: dict[str, str]) -> None:
        self.lines: queue.Queue[str] = queue.Queue()
        self.status = 0
        self.content_type = ""
        self.ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(client, headers), daemon=True)
        self._thread.start()

    def _run(self, client: LiveServer, headers: dict[str, str]) -> None:
        with httpx.stream("GET", f"{client.url}/v1/events", headers=headers, timeout=30) as response:
            self.status, self.content_type = response.status_code, response.headers.get("content-type", "")
            if response.status_code != 200:
                self.ready.set()
                self.lines.put(response.read().decode())
                return
            for line in response.iter_lines():
                if line == ": connected":
                    self.ready.set()
                self.lines.put(line)
        self.ready.set()

    def wait_ready(self) -> None:
        assert self.ready.wait(10), "the stream never said it was connected"

    def finish(self) -> list[str]:
        self._thread.join(15)
        assert not self._thread.is_alive(), "the stream did not end"
        out = []
        while not self.lines.empty():
            out.append(self.lines.get())
        return out


def events(lines: list[str]) -> list[dict[str, Any]]:
    """The data of each `data:` line, with the id of the `id:` line before it."""
    out, last_id = [], None
    for line in lines:
        if line.startswith("id: "):
            last_id = line[4:]
        elif line.startswith("data: "):
            out.append({**json.loads(line[6:]), "_id": last_id})
    return out


@pytest.fixture(scope="module")
def shared_db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"events_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield name
    mongo_replica_set.drop_database(name)


def insert(db: Database[dict[str, Any]], collection: str, doc: Any) -> None:
    db[collection].insert_one(doc.model_dump(by_alias=True))


def build(make_client: Any, mongo_uri: str, shared_db: str, fake_idp: Any, s3_storage: Any, redis_url: str,
          **settings: Any) -> LiveServer:  # fmt: skip
    client: TestClient = make_client(
        resources=open_resources, token_verifier=fake_idp.verifier(), mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=shared_db, redis_url=redis_url, s3_endpoint_url=s3_storage.endpoint_url,
        s3_access_key_id=s3_storage.access_key_id, s3_secret_access_key=s3_storage.secret_access_key,
        events_max_connection_s=2.0, **settings,
    )  # fmt: skip
    server = LiveServer(create_app(cast(FastAPI, client.app).state.settings, resources=open_resources,
                                   token_verifier=fake_idp.verifier()))  # fmt: skip
    SERVERS.append(server)
    return server


SERVERS: list[LiveServer] = []


@pytest.fixture(autouse=True)
def _stop_servers() -> Iterator[None]:
    yield
    while SERVERS:
        SERVERS.pop().close()


@pytest.fixture
def api(make_client: Any, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]], shared_db: str,
        fake_idp: Any, s3_storage: Any, redis_url: str) -> Api:  # fmt: skip
    db = mongo_replica_set[shared_db]
    for collection in COLLECTIONS:
        db[collection].delete_many({})
    db.tenants.delete_many({})
    client = build(make_client, mongo_uri, shared_db, fake_idp, s3_storage, redis_url)
    issuer = client.app.state.settings.oidc_issuer
    for tenant_id in (T, OTHER):
        insert(db, "tenants", Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id))
    for unit in ("unit-1", "unit-2"):
        insert(db, "units", Unit(id=unit, tenant_id=T, name=unit))
    for sub, (tenant_id, user_id, role, units) in USERS.items():
        insert(db, "users", User(id=user_id, tenant_id=tenant_id, email=f"{sub}@example.com", name=sub, role=role,
                                 unit_ids=units, status="active"))  # fmt: skip
        insert(db, "identities", IdentityLink(tenant_id=tenant_id, issuer=issuer, subject=sub,
                                              email=f"{sub}@example.com", user_id=user_id))  # fmt: skip
    insert(db, "people", Person(id="p-asha", tenant_id=T, name="Asha", unit_id="unit-1", user_id="u-asha"))
    insert(db, "people", Person(id="p-ravi", tenant_id=T, name="Ravi", unit_id="unit-2"))
    for rid, person, unit in (("r-asha", "p-asha", "unit-1"), ("r-ravi", "p-ravi", "unit-2")):
        insert(db, "recordings", Recording(id=rid, tenant_id=T, type=ConversationType.TEACHING,
                                           status=RecordingStatus.ANALYZING, consent_ref="c", person_id=person,
                                           unit_id=unit))  # fmt: skip
    return Api(client, db, fake_idp, redis.Redis.from_url(redis_url))


def moved(rid: str, to: RecordingStatus, *, tenant_id: str = T, minutes_ago: float = 0) -> OutboxEvent:
    return OutboxEvent(
        tenant_id=tenant_id, type=f"recording.{to.value.lower()}",
        created_at=utc_now() - timedelta(minutes=minutes_ago),
        payload={"recording_id": rid, "from_status": "ANALYZING", "to_status": to.value, "reason": "analyze_done",
                 "meta": {"note": "A reviewer's private note."}},
    )  # fmt: skip


def test_staff_receive_only_their_own_recordings(api: Api) -> None:
    listener = api.listen("asha")
    listener.wait_ready()
    assert listener.content_type.startswith("text/event-stream")
    for event in (moved("r-ravi", RecordingStatus.COMPLETED), moved("r-asha", RecordingStatus.COMPLETED)):
        api.publish(T, event)
    got = events(listener.finish())
    assert [e["recording_id"] for e in got] == ["r-asha"]
    assert set(got[0]) == {"type", "recording_id", "status", "reason", "at", "_id"}  # never the meta or a note
    assert (got[0]["type"], got[0]["status"]) == ("recording.completed", "COMPLETED")


def test_managers_see_their_units_and_owners_everything(api: Api) -> None:
    manager, owner = api.listen("manager"), api.listen("owner")
    manager.wait_ready()
    owner.wait_ready()
    for event in (moved("r-asha", RecordingStatus.COMPLETED), moved("r-ravi", RecordingStatus.FAILED)):
        api.publish(T, event)
    assert [e["recording_id"] for e in events(manager.finish())] == ["r-asha"]
    assert sorted(e["recording_id"] for e in events(owner.finish())) == ["r-asha", "r-ravi"]


def test_another_tenants_events_never_arrive(api: Api) -> None:
    stranger = api.listen("stranger")
    stranger.wait_ready()
    api.publish(T, moved("r-asha", RecordingStatus.COMPLETED))
    # Even an event naming tenant-a's recording on tenant-b's channel is not shown: the recording is not theirs.
    api.publish(OTHER, moved("r-asha", RecordingStatus.COMPLETED, tenant_id=OTHER))
    assert events(stranger.finish()) == []


def test_a_reconnect_replays_what_was_missed(api: Api) -> None:
    seen = moved("r-asha", RecordingStatus.DIARIZING, minutes_ago=3)
    missed = [moved("r-asha", RecordingStatus.TRANSCRIBING, minutes_ago=2),
              moved("r-ravi", RecordingStatus.TRANSCRIBING, minutes_ago=2),  # not hers
              moved("r-asha", RecordingStatus.ANALYZING, minutes_ago=1)]  # fmt: skip
    too_old = moved("r-asha", RecordingStatus.PREPROCESSING, minutes_ago=9)
    for event in (too_old, seen, *missed):
        insert(api.db, "outbox", event.model_copy(update={"published_at": event.created_at}))
    insert(api.db, "outbox", moved("r-asha", RecordingStatus.COMPLETED))  # not published yet: comes live
    got = events(api.listen("asha", last_event_id=seen.id).finish())
    assert [(e["_id"], e["status"]) for e in got] == [(missed[0].id, "TRANSCRIBING"), (missed[2].id, "ANALYZING")]


def test_an_unknown_last_event_id_replays_the_last_five_minutes(api: Api) -> None:
    recent = moved("r-asha", RecordingStatus.TRANSCRIBING, minutes_ago=1)
    old = moved("r-asha", RecordingStatus.DIARIZING, minutes_ago=9)
    for event in (old, recent):
        insert(api.db, "outbox", event.model_copy(update={"published_at": event.created_at}))
    got = events(api.listen("asha", last_event_id="no-such-event").finish())
    assert [e["_id"] for e in got] == [recent.id]


def test_a_heartbeat_keeps_the_connection_alive(make_client: Any, mongo_uri: str, shared_db: str, fake_idp: Any,
                                                s3_storage: Any, redis_url: str, api: Api) -> None:  # fmt: skip
    client = build(make_client, mongo_uri, shared_db, fake_idp, s3_storage, redis_url, events_heartbeat_s=0.4)
    lines = Listener(client, {"Authorization": f"Bearer {fake_idp.token('asha')}"}).finish()
    assert lines.count(": ping") >= 2


def test_sign_in_is_required(api: Api) -> None:
    listener = api.listen(None)
    listener.finish()
    assert listener.status == 401


def test_without_redis_the_app_is_told_to_keep_polling(make_client: Any, mongo_uri: str, shared_db: str,
                                                       fake_idp: Any, s3_storage: Any, api: Api) -> None:  # fmt: skip
    client = build(make_client, mongo_uri, shared_db, fake_idp, s3_storage, "redis://127.0.0.1:1/0")
    listener = Listener(client, {"Authorization": f"Bearer {fake_idp.token('asha')}"})
    body = "".join(listener.finish())
    assert listener.status == 503 and json.loads(body)["code"] == "live_unavailable"
