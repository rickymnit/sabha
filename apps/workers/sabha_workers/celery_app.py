"""The Celery app: queues, routing and reliability settings for every worker (plan task P2.4).

Run a worker with the queues it serves, for example:

    celery -A sabha_workers.worker worker -Q cpu.preprocess,io.notify,billing.meter,llm.analyze,llm.analyze.priority
    celery -A sabha_workers.worker worker -Q gpu.speech.priority,gpu.speech --concurrency 1
    celery -A sabha_workers.worker beat

Reliability: tasks are acknowledged only after they finish (`acks_late`), and a task whose worker dies is
redelivered (`reject_on_worker_lost`). With the Redis broker, the dead worker's message waits in `unacked` until
CELERY_VISIBILITY_TIMEOUT_S has passed, and a live worker then restores it on its next restore pass; Kombu makes
one pass about every 100 s (measured in tests/test_worker_kill.py). The timeout must outlast the longest stage, so
for GPU workers it is hours: the stuck-job sweeper (sabha_workers.maintenance) re-sends a stage much sooner, once
its heartbeat has been silent for STUCK_AFTER_S. A late duplicate is harmless: the runner sees the stage is done.
Each worker takes one task at a time (prefetch 1), so a long GPU job never holds others hostage. Results are not
stored: progress lives in MongoDB (recordings, stage_runs) and every stage is idempotent (golden rule 3).
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from kombu import Queue

from sabha_core.queues import BILLING_METER, CPU_PREPROCESS, GPU_SPEECH, IO_NOTIFY, LLM_ANALYZE, all_queues
from sabha_core.settings import Settings

TASK_QUEUES: dict[str, str] = {
    "sabha.preprocess": CPU_PREPROCESS,
    "sabha.diarize": GPU_SPEECH,
    "sabha.transcribe": GPU_SPEECH,
    "sabha.analyze": LLM_ANALYZE,
    "sabha.notify": IO_NOTIFY,
    "sabha.meter": BILLING_METER,
    "sabha.maintenance.abort_stale_uploads": IO_NOTIFY,
    "sabha.maintenance.requeue_stuck": IO_NOTIFY,
    "sabha.maintenance.expire_audio": IO_NOTIFY,  # nightly audio retention (P7.3)
}


def route(name: str, args: Any, kwargs: Any, options: Any, task: Any = None, **_: Any) -> dict[str, str] | None:
    queue = TASK_QUEUES.get(name)
    return {"queue": queue} if queue else None


def create_app(settings: Settings) -> Celery:
    app = Celery("sabha", broker=settings.redis_url.get_secret_value())
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_queues=[Queue(name) for name in all_queues()],
        task_default_queue=IO_NOTIFY,
        task_routes=(route,),
        broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout_s},
        broker_connection_retry_on_startup=True,
        worker_hijack_root_logger=False,
        beat_schedule={
            "abort-stale-uploads": {"task": "sabha.maintenance.abort_stale_uploads", "schedule": 3600.0},
            "requeue-stuck": {"task": "sabha.maintenance.requeue_stuck", "schedule": 300.0},
            "expire-audio": {"task": "sabha.maintenance.expire_audio", "schedule": 86_400.0},  # P7.3, daily
        },
    )
    return app
