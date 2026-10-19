"""Celery task definitions (plan task P2.4). Each pipeline stage task is a thin wrapper around StageRunner.

Stages not built yet (P3.2 preprocess, P3.4 diarize, P3.5 transcribe, P5.7 analyze) fail honestly with
`stage_not_built`: the recording goes to FAILED with a dead letter, so nothing silently stalls and the job can be
replayed once the stage exists (P7.8). notify and meter only log until P2.7 and P8.6 wire them.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import timedelta
from functools import cache
from typing import Any

import boto3
from botocore.config import Config
from celery import Celery, Task
from pymongo.database import Database

from sabha_core.models import utc_now
from sabha_core.mongo import open_sync
from sabha_core.settings import Settings, get_settings
from sabha_core.state import RecordingStatus
from sabha_workers.dispatch import CeleryDispatcher
from sabha_workers.maintenance import requeue_stuck
from sabha_workers.stages.runner import PermanentError, S3Artefacts, StageContext, StageRunner, StageSpec, Work
from sabha_workers.upload_cleanup import abort_stale_uploads

log = logging.getLogger("sabha.workers.tasks")
S = RecordingStatus

SPECS: dict[str, StageSpec] = {
    "preprocess": StageSpec("preprocess", working=S.PREPROCESSING, done_to=S.DIARIZING, entry_from=S.UPLOADED),
    "diarize": StageSpec("diarize", working=S.DIARIZING, done_to=S.TRANSCRIBING),
    "transcribe": StageSpec("transcribe", working=S.TRANSCRIBING, done_to=S.ANALYZING),
    "analyze": StageSpec("analyze", working=S.ANALYZING, done_to=S.COMPLETED),
}


def not_built(stage: str) -> Work:
    def work(ctx: StageContext) -> dict[str, Any] | None:
        raise PermanentError("stage_not_built", f"the {stage} stage is not implemented yet")

    return work


WORKS: dict[str, Work] = {name: not_built(name) for name in SPECS}


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    db: Database[dict[str, Any]]
    s3: Any
    runner: StageRunner


def s3_client(settings: Settings) -> Any:
    keys: dict[str, str] = {}
    if settings.s3_access_key_id is not None and settings.s3_secret_access_key is not None:
        keys = {
            "aws_access_key_id": settings.s3_access_key_id.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
        }
    config = Config(s3={"addressing_style": "path"} if settings.s3_endpoint_url else {})
    return boto3.client(
        "s3", region_name=settings.s3_region, endpoint_url=settings.s3_endpoint_url, config=config, **keys
    )


@cache
def runtime() -> Runtime:
    """One MongoDB client, S3 client and runner per worker process, created on first use."""
    settings = get_settings()
    _, db = open_sync(settings)
    s3 = s3_client(settings)
    versions = {
        "preprocess": settings.artefact_version_preprocess,
        "diarize": settings.artefact_version_diarize,
        "transcribe": settings.artefact_version_transcribe,
        "analyze": settings.artefact_version_analyze,
    }
    runner = StageRunner(
        db=db,
        artefacts=S3Artefacts(s3, settings.s3_bucket_artefacts),
        versions=versions,
        worker=f"{socket.gethostname()}:{os.getpid()}",
        max_attempts=settings.stage_max_attempts,
    )
    return Runtime(settings, db, s3, runner)


def register(app: Celery) -> None:
    """Define every task on `app`."""

    def stage_task(name: str) -> None:
        @app.task(bind=True, name=f"sabha.{name}", acks_late=True, reject_on_worker_lost=True, max_retries=None)
        def run(self: Task, tenant_id: str, recording_id: str) -> str:
            outcome = runtime().runner.run(SPECS[name], WORKS[name], tenant_id, recording_id,
                                           attempt=self.request.retries + 1)  # fmt: skip
            if outcome.result == "retry":
                raise self.retry(countdown=outcome.retry_in)
            return outcome.result

    for stage in SPECS:
        stage_task(stage)

    @app.task(name="sabha.notify", acks_late=True)
    def notify(tenant_id: str, recording_id: str) -> str:
        log.info("notify is not wired yet (P2.7)", extra={"recording_id": recording_id})
        return "not_built"

    @app.task(name="sabha.meter", acks_late=True)
    def meter(tenant_id: str, recording_id: str) -> str:
        log.info("metering is not wired yet (P8.6)", extra={"recording_id": recording_id})
        return "not_built"

    @app.task(name="sabha.maintenance.abort_stale_uploads", acks_late=True)
    def abort_stale() -> int:
        rt = runtime()
        return len(abort_stale_uploads(rt.s3, rt.settings.s3_bucket_audio))

    @app.task(name="sabha.maintenance.requeue_stuck", acks_late=True)
    def requeue() -> int:
        rt = runtime()
        dispatcher = CeleryDispatcher(app)
        return requeue_stuck(
            rt.db,
            lambda stage, tenant_id, recording_id: dispatcher.send_stage(stage, tenant_id, recording_id),
            stuck_after=timedelta(seconds=rt.settings.stuck_after_s),
            now=utc_now(),
        )
