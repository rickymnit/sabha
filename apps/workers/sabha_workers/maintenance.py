"""Periodic maintenance (plan task P2.4): re-send pipeline stages that got stuck.

A stage is stuck when its recording has stayed in that stage's status longer than STUCK_AFTER_S and its latest
stage run is not alive (no heartbeat within that time). That happens when a worker vanished in a way Celery could
not redeliver (for example the broker lost the message). Re-sending is safe: stages are idempotent.

Tenants are swept one by one through the tenant-scoped repository; only the tenant list itself is read with
SyncSystemRepo (allowed for this module in tests/security/test_raw_collection_access.py).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from pymongo.database import Database

from sabha_core.models import Recording, StageRun, Tenant
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.state import RecordingStatus

log = logging.getLogger("sabha.workers.maintenance")

STAGE_FOR_STATUS: dict[RecordingStatus, str] = {
    RecordingStatus.PREPROCESSING: "preprocess",
    RecordingStatus.DIARIZING: "diarize",
    RecordingStatus.TRANSCRIBING: "transcribe",
    RecordingStatus.ANALYZING: "analyze",
}

Send = Callable[[str, str, str], None]  # (stage, tenant_id, recording_id)


def requeue_stuck(db: Database[dict[str, Any]], send: Send, *, stuck_after: timedelta, now: datetime) -> int:
    """Re-send every stuck stage; returns how many were re-sent."""
    cutoff = now - stuck_after
    sent = 0
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    for tenant in tenants.find({}):
        recordings = SyncTenantRepo(db, "recordings", tenant.id, Recording)
        runs = SyncTenantRepo(db, "stage_runs", tenant.id, StageRun)
        stuck = recordings.find(
            {"status": {"$in": [s.value for s in STAGE_FOR_STATUS]}, "status_changed_at": {"$lt": cutoff}}
        )
        for recording in stuck:
            stage = STAGE_FOR_STATUS[recording.status]
            latest = runs.find({"recording_id": recording.id, "stage": stage}, sort=[("attempt", -1)], limit=1)
            if latest and latest[0].status == "running" and (latest[0].heartbeat_at or latest[0].started_at) > cutoff:
                continue  # still alive
            log.warning("re-sending a stuck stage", extra={"recording_id": recording.id, "stage": stage})
            send(stage, tenant.id, recording.id)
            sent += 1
    return sent
