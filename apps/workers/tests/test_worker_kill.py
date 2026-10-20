"""Killing a worker mid-job loses nothing (plan task P2.4 "Done when"): a real Celery worker process is killed
with SIGKILL while a stage runs; another worker gets the task again and the stage completes exactly once.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database
from redis import Redis

from sabha_core.indexes import ensure_indexes
from sabha_core.models import Recording
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import Settings
from sabha_core.state import RecordingStatus
from sabha_workers.celery_app import create_app
from sabha_workers.dispatch import CeleryDispatcher

pytestmark = pytest.mark.integration
HERE = Path(__file__).parent
VISIBILITY_S = 5


def wait_for(condition: Callable[[], bool], timeout_s: float, what: str) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.2)


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"kill_{uuid.uuid4().hex[:12]}"
    ensure_indexes(mongo_replica_set[name])
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def start_worker(env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "kill_app", "worker", "-Q", "cpu.preprocess", "--pool", "solo",
         "--without-heartbeat", "--without-gossip", "--without-mingle", "-l", "warning"],
        cwd=HERE, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip


def stop(worker: subprocess.Popen[bytes], sig: int) -> None:
    os.killpg(worker.pid, sig)
    worker.wait(timeout=30)


def test_a_killed_worker_loses_nothing(
    db: Database[dict[str, Any]], mongo_uri: str, redis_url: str, s3_storage: Any
) -> None:
    Redis.from_url(redis_url).flushdb()
    rid = (
        SyncTenantRepo(db, "recordings", "t1", Recording)
        .insert_one(Recording(type=ConversationType.TEACHING, status=RecordingStatus.UPLOADED, consent_ref="c"))
        .id
    )
    env = {
        **os.environ,
        "PYTHONPATH": f"{HERE}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
        "KILL_MONGO_URI": f"{mongo_uri}&replicaSet=rs0",
        "KILL_DB": db.name,
        "KILL_REDIS_URL": redis_url,
        "KILL_S3_URL": s3_storage.endpoint_url,
        "KILL_S3_KEY": s3_storage.access_key_id,
        "KILL_S3_SECRET": s3_storage.secret_access_key,
        "KILL_VISIBILITY_S": str(VISIBILITY_S),
        "KILL_WORK_S": "4",
    }
    values: dict[str, Any] = {
        "app_env": "test",
        "mongo_uri": f"{mongo_uri}&replicaSet=rs0",
        "redis_url": redis_url,
        "s3_bucket_audio": "a",
        "s3_bucket_artefacts": "b",
        "s3_bucket_backups": "c",
        "oidc_issuer": "https://auth.example.com",
        "oidc_audience": "https://api.example.com",
        "oidc_client_id": "web",
        "celery_visibility_timeout_s": VISIBILITY_S,
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[call-arg]  # pydantic-settings
    CeleryDispatcher(create_app(settings)).send_stage("preprocess", "t1", rid)

    first = start_worker(env)
    try:
        wait_for(lambda: db.work_log.count_documents({}) == 1, 60, "the first worker to start the stage")
    finally:
        stop(first, signal.SIGKILL)  # mid-job, no chance to acknowledge or clean up
    assert db.recordings.find_one({"_id": rid})["status"] == "PREPROCESSING"  # type: ignore[index]  # inserted above

    second = start_worker(env)
    try:
        wait_for(
            lambda: (db.recordings.find_one({"_id": rid}) or {}).get("status") == "DIARIZING",
            180,  # Kombu restores unacknowledged messages only every ~100 s (see sabha_workers.celery_app)
            "the redelivered task to finish the stage",
        )
        time.sleep(VISIBILITY_S + 2)  # long enough for any duplicate delivery to show up
    finally:
        stop(second, signal.SIGTERM)

    runs = list(db.stage_runs.find({"recording_id": rid}).sort("attempt", 1))
    assert [r["status"] for r in runs] == ["running", "succeeded"]  # the killed attempt, then the one that finished
    assert [e["type"] for e in db.outbox.find({"payload.recording_id": rid}).sort("created_at", 1)] == [
        "recording.preprocessing",
        "recording.diarizing",
    ]  # one transition each: completed exactly once
