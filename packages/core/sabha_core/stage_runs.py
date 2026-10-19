"""Stage runs: one document per attempt of a pipeline stage for a recording (plan task P2.3).

Workers call `start_stage_run` when a stage task begins and `finish_stage_run` when it ends. Attempts are numbered
from 1 per (recording, stage, version); the unique index on those plus the attempt makes two workers starting at
once get different numbers (a loser of the race retries with the next number). `meta` holds measured cost inputs
(audio seconds, GPU seconds, tokens); cost itself is computed later from them (golden rule 6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.client_session import ClientSession
from pymongo.errors import DuplicateKeyError

from sabha_core.models import StageRun, utc_now
from sabha_core.repo import SyncTenantRepo

MAX_ERROR_DETAIL = 2000
_START_RETRIES = 25


def start_stage_run(
    runs: SyncTenantRepo[StageRun],
    recording_id: str,
    stage: str,
    version: str,
    *,
    worker: str,
    now: datetime | None = None,
    session: ClientSession | None = None,
) -> StageRun:
    """Insert a running attempt numbered one past the latest for (recording, stage, version)."""
    key = {"recording_id": recording_id, "stage": stage, "version": version}
    for _ in range(_START_RETRIES):
        latest = runs.find(key, sort=[("attempt", -1)], limit=1, session=session)
        attempt = latest[0].attempt + 1 if latest else 1
        run = StageRun(
            recording_id=recording_id,
            stage=stage,
            version=version,
            attempt=attempt,
            worker=worker,
            started_at=now or utc_now(),
        )
        try:
            return runs.insert_one(run, session=session)
        except DuplicateKeyError:
            continue  # another worker took this attempt number
    raise RuntimeError(f"could not number a stage run for {recording_id}/{stage}@{version}")


def finish_stage_run(
    runs: SyncTenantRepo[StageRun],
    run: StageRun,
    *,
    succeeded: bool,
    error_code: str | None = None,
    error_detail: str | None = None,
    meta: dict[str, Any] | None = None,
    now: datetime | None = None,
    session: ClientSession | None = None,
) -> StageRun:
    """Mark the attempt succeeded or failed, with its duration; returns the updated run."""
    finished = now or utc_now()
    changes: dict[str, Any] = {
        "status": "succeeded" if succeeded else "failed",
        "finished_at": finished,
        "duration_ms": max(0, round((finished - run.started_at).total_seconds() * 1000)),
        "error_code": error_code,
        "error_detail": error_detail[:MAX_ERROR_DETAIL] if error_detail else error_detail,
        "meta": {**run.meta, **(meta or {})},
    }
    runs.update_one({"_id": run.id, "status": "running"}, {"$set": changes}, session=session)
    return run.model_copy(update=changes)
