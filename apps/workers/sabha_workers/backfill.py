"""Fill in fields added after recordings were processed (UI v2), from the artefacts already in storage. Safe to run
again: it only touches documents still missing the field. Run by hand with scripts/admin/backfill.py.

- speaker strips: each transcript's `speaker_strip` from its transcript@v1.json (sabha_workers.stages.transcript);
- speech: each recording's `speech_ms` from the preprocess stage's segments@v1.json (the compact length);
- tickets: each reception analysis's `ticket_status`, `ticket_category` and `ticket_follow_up` from its report
  (sabha_workers.stages.analyze.ticket_fields).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from sabha_core.models import Analysis, Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_workers.stages.analyze import ticket_fields
from sabha_workers.stages.transcript import speaker_strip

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Filled:
    tenant_id: str
    strips: int
    speech: int
    tickets: int
    missing_files: int


class _Files:
    def __init__(self, s3: Any, bucket: str) -> None:
        self.s3, self.bucket, self.missing = s3, bucket, 0

    def json(self, key: str) -> Any | None:
        try:
            return json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        except self.s3.exceptions.NoSuchKey:
            self.missing += 1
            log.warning("backfill: file missing", extra={"key": key})
            return None


def backfill(
    db: Database[dict[str, Any]], s3: Any, *, artefacts_bucket: str, preprocess_version: str, dry_run: bool = False
) -> list[Filled]:
    """Every backfill, tenant by tenant; returns what was (or, in a dry run, would be) filled in."""
    done = []
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    for tenant in tenants.find({}):
        files = _Files(s3, artefacts_bucket)
        transcripts = SyncTenantRepo(db, "transcripts", tenant.id, Transcript)
        recordings = SyncTenantRepo(db, "recordings", tenant.id, Recording)
        analyses = SyncTenantRepo(db, "analyses", tenant.id, Analysis)

        strips = 0
        for doc in transcripts.find({"speaker_strip": {"$in": [None, []]}}):
            content = files.json(doc.storage_key)
            if content is None:
                continue
            recording = recordings.find_one({"_id": doc.recording_id})
            meeting = recording is not None and recording.type is ConversationType.MEETING
            staff = None if meeting or not doc.role_choices else doc.role_choices[0]
            strip = speaker_strip(content["utterances"], staff, recording.duration_ms if recording else None)
            if strip:
                strips += 1
                if not dry_run:
                    transcripts.update_one(
                        {"_id": doc.id}, {"$set": {"speaker_strip": [s.model_dump() for s in strip]}}
                    )

        speech = 0
        for recording in recordings.find({"speech_ms": None, "duration_ms": {"$ne": None}}):
            prefix = artefact_prefix(tenant.id, recording.id, "preprocess", preprocess_version)
            content = files.json(prefix + "segments@v1.json")
            if content is None:
                continue
            speech += 1
            if not dry_run:
                speech_ms = SegmentMap.from_json(json.dumps(content)).compact_length_ms
                recordings.update_one({"_id": recording.id}, {"$set": {"speech_ms": speech_ms}})

        tickets = 0
        for analysis in analyses.find({"conversation_type": ConversationType.RECEPTION.value, "ticket_status": None}):
            report = files.json(analysis.report_key)
            fields = ticket_fields(report) if report is not None else {}
            if fields:
                tickets += 1
                if not dry_run:
                    analyses.update_one({"_id": analysis.id}, {"$set": fields})

        if strips or speech or tickets or files.missing:
            done.append(Filled(tenant.id, strips, speech, tickets, files.missing))
    return done
