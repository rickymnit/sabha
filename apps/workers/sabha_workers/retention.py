"""Audio retention (plan task P7.3): delete each recording's audio once it is older than its tenant's
retention_days (90 by default, sabha_core.profiles).

Nightly, per tenant: recordings uploaded before the cutoff whose audio is still there and that are not being
processed lose their original (audio bucket) and their audio working copies (normalised.wav, compact.wav,
playback.opus in the artefacts bucket). Transcripts, reports, scores and disputes stay. Each recording is marked
audio_deleted_at; each tenant's run writes one audit entry (audio.expire) with the ids. A dry run only counts.

Tenants are read with SyncSystemRepo (allowed for this module in tests/security/test_raw_collection_access.py), then
handled one by one through the tenant-scoped repository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pymongo.database import Database

from sabha_core.models import AuditEntry, Recording, Tenant
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.state import WORKER_STAGES
from sabha_core.storage import delete_objects, is_audio_key, recording_prefix

log = logging.getLogger("sabha.workers.retention")

BATCH = 500  # recordings per tenant per run; the rest wait for the next night


@dataclass(frozen=True, slots=True)
class Expired:
    tenant_id: str
    recordings: int
    objects: int


def expire_audio(
    db: Database[dict[str, Any]], s3: Any, *, audio_bucket: str, artefacts_bucket: str, now: datetime,
    dry_run: bool = False,
) -> list[Expired]:  # fmt: skip
    """Delete expired audio for every tenant; returns what was (or, in a dry run, would be) deleted."""
    done = []
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    for tenant in tenants.find({}):
        recordings = SyncTenantRepo(db, "recordings", tenant.id, Recording)
        expired = recordings.find(
            {
                "created_at": {"$lt": now - timedelta(days=tenant.retention_days)},
                "audio_deleted_at": None,
                "status": {"$nin": [s.value for s in WORKER_STAGES]},  # never under a running stage
            },
            sort=[("created_at", 1)],
            limit=BATCH,
        )
        if not expired:
            continue
        objects = 0
        for recording in expired:
            prefix = recording_prefix(tenant.id, recording.id)
            objects += delete_objects(s3, audio_bucket, prefix, dry_run=dry_run)
            objects += delete_objects(s3, artefacts_bucket, prefix, only=is_audio_key, dry_run=dry_run)
            if not dry_run:
                recordings.update_one({"_id": recording.id, "audio_deleted_at": None},
                                      {"$set": {"audio_deleted_at": now}})  # fmt: skip
        if not dry_run:
            entries = SyncTenantRepo(db, "audit_log", tenant.id, AuditEntry)
            entries.insert_one(
                AuditEntry(
                    actor_user_id="system",
                    actor_role="system",
                    action="audio.expire",
                    target_type="tenant",
                    target_id=tenant.id,
                    at=now,
                    meta={
                        "retention_days": tenant.retention_days,
                        "recording_ids": [r.id for r in expired],
                        "objects": objects,
                    },
                )
            )
        log.info("audio expired", extra={"tenant_id": tenant.id, "recordings": len(expired), "dry_run": dry_run})
        done.append(Expired(tenant.id, len(expired), objects))
    return done
