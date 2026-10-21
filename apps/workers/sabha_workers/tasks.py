"""Celery task definitions (plan task P2.4). Each pipeline stage task is a thin wrapper around StageRunner.

preprocess (P3.2, P3.3) and diarize (P3.4) are in sabha_workers.stages. Stages not built yet (P3.5 transcribe,
P5.7 analyze) fail honestly with
`stage_not_built`: the recording goes to FAILED with a dead letter, so nothing silently stalls and the job can be
replayed once the stage exists (P7.8). notify sends the status emails (P2.7, sabha_workers.notifications.notify);
meter only logs until P8.6.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from celery import Celery, Task
from pymongo.database import Database

from sabha_asr.diarization import DEFAULT_MODEL_DIR as DEFAULT_PYANNOTE_DIR
from sabha_asr.diarization import Diarizer, PyannoteDiarizer, ScriptedDiarizer
from sabha_core.models import AudioInfo, Recording, utc_now
from sabha_core.mongo import open_sync
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import Settings, get_settings
from sabha_core.state import RecordingStatus
from sabha_workers.dispatch import CeleryDispatcher
from sabha_workers.maintenance import requeue_stuck
from sabha_workers.notifications.notify import notify as send_notifications
from sabha_workers.notifications.ses import EmailSender, RetryableSendError, SesSender
from sabha_workers.stages import diarize, preprocess
from sabha_workers.stages.runner import PermanentError, S3Artefacts, StageContext, StageRunner, StageSpec, Work
from sabha_workers.stages.vad import DEFAULT_MODEL_PATH, SileroVad
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


NOTIFY_MAX_RETRIES = 8  # SES throttling or outage: waits double from 1 min, capped at 1 h


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    db: Database[dict[str, Any]]
    s3: Any
    runner: StageRunner
    works: dict[str, Work]
    sender: EmailSender | None  # None without SES_SENDER: notify logs and sends nothing


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
    sender = SesSender.from_settings(settings) if settings.ses_sender else None
    return Runtime(settings, db, s3, runner, works(db, s3, settings), sender)


def works(db: Database[dict[str, Any]], s3: Any, settings: Settings) -> dict[str, Work]:
    def record_audio(tenant_id: str, recording_id: str, duration_ms: int, audio: AudioInfo) -> None:
        recordings = SyncTenantRepo(db, "recordings", tenant_id, Recording)
        recordings.update_one(
            {"_id": recording_id}, {"$set": {"duration_ms": duration_ms, "audio": audio.model_dump()}}
        )

    @cache
    def vad() -> SileroVad:  # loaded on the first preprocess task only, then reused
        return SileroVad(Path(settings.vad_model_path) if settings.vad_model_path else DEFAULT_MODEL_PATH)

    params = preprocess.VadParams(
        threshold=settings.vad_threshold, min_speech_ms=settings.vad_min_speech_ms,
        min_silence_ms=settings.vad_min_silence_ms, end_pad_ms=settings.vad_end_pad_ms,
        merge_gap_ms=settings.vad_merge_gap_ms,
    )  # fmt: skip
    originals = preprocess.S3Originals(s3, settings.s3_bucket_audio)

    @cache
    def diarizer() -> Diarizer:  # loaded on the first diarize task only (pyannote is an optional install)
        if settings.diarizer == "fake":  # APP_ENV=test only (settings): one speaker for the whole file
            return ScriptedDiarizer([("A", 0, 2**62)])
        model_dir = Path(settings.diarization_model_dir) if settings.diarization_model_dir else None
        return PyannoteDiarizer(
            model_dir or DEFAULT_PYANNOTE_DIR, settings.diarization_device, settings.diarization_batch_size
        )

    built = {
        "preprocess": preprocess.make_work(originals, record_audio, vad, params),
        "diarize": diarize.make_work(diarizer, settings.artefact_version_preprocess, settings.diarization_device),
    }
    return {name: built.get(name) or not_built(name) for name in SPECS}


def register(app: Celery) -> None:
    """Define every task on `app`."""

    def stage_task(name: str) -> None:
        @app.task(bind=True, name=f"sabha.{name}", acks_late=True, reject_on_worker_lost=True, max_retries=None)
        def run(self: Task, tenant_id: str, recording_id: str, event_id: str | None = None) -> str:
            rt = runtime()
            outcome = rt.runner.run(SPECS[name], rt.works[name], tenant_id, recording_id,
                                    attempt=self.request.retries + 1)  # fmt: skip
            if outcome.result == "retry":
                raise self.retry(countdown=outcome.retry_in)
            return outcome.result

    for stage in SPECS:
        stage_task(stage)

    @app.task(bind=True, name="sabha.notify", acks_late=True, max_retries=NOTIFY_MAX_RETRIES)
    def notify(self: Task, tenant_id: str, recording_id: str, event_id: str | None = None) -> str:
        if event_id is None:
            log.warning("notify needs the event that started it", extra={"recording_id": recording_id})
            return "no_event"
        rt = runtime()
        try:
            result = send_notifications(
                rt.db, tenant_id=tenant_id, recording_id=recording_id, event_id=event_id,
                sender=rt.sender, web_base_url=rt.settings.web_base_url,
            )  # fmt: skip
        except RetryableSendError as exc:
            raise self.retry(exc=exc, countdown=min(3600, 60 * 2**self.request.retries)) from exc
        return f"sent={result.sent} skipped={result.skipped} failed={result.failed}"

    @app.task(name="sabha.meter", acks_late=True)
    def meter(tenant_id: str, recording_id: str, event_id: str | None = None) -> str:
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
