"""The Celery app, task registry, dispatcher and stuck-job sweeper (plan task P2.4)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, cast

import pytest
from pymongo import MongoClient
from pymongo.database import Database
from redis import Redis

from sabha_core.indexes import ensure_indexes
from sabha_core.models import OutboxEvent, Recording, StageRun, Tenant, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.queues import all_queues
from sabha_core.quota import Plan
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_workers.celery_app import TASK_QUEUES, create_app, route
from sabha_workers.dispatch import CeleryDispatcher
from sabha_workers.maintenance import requeue_stuck
from sabha_workers.tasks import SPECS, register

BASE: dict[str, Any] = {
    "app_env": "test",
    "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
    "s3_bucket_audio": "sabha-audio",
    "s3_bucket_artefacts": "sabha-artefacts",
    "s3_bucket_backups": "sabha-backups",
    "oidc_issuer": "https://auth.example.com",
    "oidc_audience": "https://api.example.com",
    "oidc_client_id": "web",
}


def settings(redis_url: str = "redis://localhost:6380/0") -> Settings:
    return Settings(_env_file=None, **{**BASE, "redis_url": redis_url})  # type: ignore[call-arg]  # pydantic-settings


# --- Configuration ---


def test_reliability_settings() -> None:
    conf = create_app(settings()).conf
    assert conf.task_acks_late is True and conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.broker_transport_options["visibility_timeout"] == 4 * 3600
    assert {q.name for q in conf.task_queues} == set(all_queues())


def test_every_task_is_registered_and_routed() -> None:
    app = create_app(settings())
    register(app)
    names = {name for name in app.tasks if name.startswith("sabha.")}
    assert names == set(TASK_QUEUES)
    assert route("sabha.diarize", (), {}, {}) == {"queue": "gpu.speech"}
    assert route("celery.chord_unlock", (), {}, {}) is None
    assert set(SPECS) == {"preprocess", "diarize", "transcribe", "analyze"}


def test_beat_runs_the_maintenance_tasks() -> None:
    schedule = create_app(settings()).conf.beat_schedule
    assert {entry["task"] for entry in schedule.values()} == {
        "sabha.maintenance.abort_stale_uploads",
        "sabha.maintenance.requeue_stuck",
        "sabha.maintenance.expire_audio",
        "sabha.maintenance.backup",
    }


# --- Dispatcher, against a real Redis broker ---


@pytest.mark.integration
def test_the_dispatcher_puts_the_task_on_its_queue(redis_url: str) -> None:
    redis = Redis.from_url(redis_url)
    redis.flushdb()
    dispatcher = CeleryDispatcher(create_app(settings(redis_url)))
    event = OutboxEvent(id="ev1", tenant_id="t1", type="recording.diarizing", payload={"recording_id": "r1"})
    dispatcher.send("diarize", event)
    (raw,) = cast(list[bytes], redis.lrange("gpu.speech", 0, -1))  # sync client: a list
    message = json.loads(raw)
    assert message["headers"]["task"] == "sabha.diarize" and message["headers"]["id"] == "ev1.diarize"
    assert redis.llen("cpu.preprocess") == 0
    redis.close()


# --- The stuck-job sweeper ---


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"sweep_{uuid.uuid4().hex[:12]}"
    database = mongo_replica_set[name]
    ensure_indexes(database)
    for tenant_id in ("t1", "t2"):
        tenant = Tenant.from_profile("school", name=tenant_id, plan=Plan.PILOT, id=tenant_id)
        database.tenants.insert_one(tenant.model_dump(by_alias=True))
    yield database
    mongo_replica_set.drop_database(name)


def recording(db: Database[dict[str, Any]], tenant: str, status: RecordingStatus, minutes_ago: int) -> str:
    rec = Recording(
        type=ConversationType.TEACHING, status=status, consent_ref="c",
        status_changed_at=utc_now() - timedelta(minutes=minutes_ago),
    )  # fmt: skip
    return SyncTenantRepo(db, "recordings", tenant, Recording).insert_one(rec).id


@pytest.mark.integration
def test_stuck_stages_are_re_sent_and_live_ones_left(db: Database[dict[str, Any]]) -> None:
    stuck = recording(db, "t1", RecordingStatus.DIARIZING, minutes_ago=90)
    other_tenant = recording(db, "t2", RecordingStatus.PREPROCESSING, minutes_ago=90)
    recent = recording(db, "t1", RecordingStatus.TRANSCRIBING, minutes_ago=5)
    alive = recording(db, "t1", RecordingStatus.ANALYZING, minutes_ago=90)
    recording(db, "t1", RecordingStatus.COMPLETED, minutes_ago=90)
    SyncTenantRepo(db, "stage_runs", "t1", StageRun).insert_one(
        StageRun(recording_id=alive, stage="analyze", version="v1", attempt=1, worker="w",
                 started_at=utc_now() - timedelta(minutes=90), heartbeat_at=utc_now() - timedelta(minutes=1))
    )  # fmt: skip
    sent: list[tuple[str, str, str]] = []
    count = requeue_stuck(db, lambda *a: sent.append(a), stuck_after=timedelta(minutes=30), now=utc_now())
    assert count == 2
    assert sorted(sent) == sorted([("diarize", "t1", stuck), ("preprocess", "t2", other_tenant)])
    assert all(recording_id not in (recent, alive) for _, _, recording_id in sent)
