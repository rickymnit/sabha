"""Fill in fields added after recordings were processed (UI v2), from the artefacts already in storage. Safe to run
again: it only touches documents still missing the field. Run by hand with scripts/admin/backfill.py.

- speaker strips: each transcript's `speaker_strip` from its transcript@v1.json (sabha_workers.stages.transcript).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from sabha_core.models import Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_workers.stages.transcript import speaker_strip

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Filled:
    tenant_id: str
    strips: int
    missing_files: int


def backfill_strips(
    db: Database[dict[str, Any]], s3: Any, *, artefacts_bucket: str, dry_run: bool = False
) -> list[Filled]:
    """Speaker strips for transcripts saved before the strip existed, tenant by tenant."""
    done = []
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    for tenant in tenants.find({}):
        transcripts = SyncTenantRepo(db, "transcripts", tenant.id, Transcript)
        recordings = SyncTenantRepo(db, "recordings", tenant.id, Recording)
        filled = missing = 0
        for doc in transcripts.find({"speaker_strip": {"$in": [None, []]}}):
            recording = recordings.find_one({"_id": doc.recording_id})
            try:
                body = s3.get_object(Bucket=artefacts_bucket, Key=doc.storage_key)["Body"].read()
            except s3.exceptions.NoSuchKey:
                missing += 1
                log.warning("backfill: transcript file missing", extra={"key": doc.storage_key})
                continue
            meeting = recording is not None and recording.type is ConversationType.MEETING
            staff = None if meeting or not doc.role_choices else doc.role_choices[0]
            strip = speaker_strip(json.loads(body)["utterances"], staff, recording.duration_ms if recording else None)
            if not strip:
                continue
            filled += 1
            if not dry_run:
                transcripts.update_one(
                    {"_id": doc.id}, {"$set": {"speaker_strip": [span.model_dump() for span in strip]}}
                )
        if filled or missing:
            done.append(Filled(tenant.id, filled, missing))
    return done
