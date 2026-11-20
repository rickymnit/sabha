"""Re-analysis (plan task P2.8, owner's decisions 2026-10-26): scoring finished recordings again from their
transcripts.

- POST /v1/recordings/{id}/reanalyze {reason, rubric_id?} (Idempotency-Key): owners and admins. The recording must
  be COMPLETED and have a transcript. One transaction: the next `analysis_run` and the chosen rubric (if any, of
  the same type, and its file must exist) on the recording, COMPLETED -> ANALYZING (allowed only with
  reanalysis=True) with its outbox event, which starts the analyze stage again; open disputes on the recording are
  closed ("Re-analysed": reviewers' scores stay with the old version, the new one starts fresh); and the audit entry
  (recording.reanalyze, with the reason). Nothing before the analyze stage runs again, so no speech recognition and
  no audio hours are billed twice; the run's end is quiet (no email, no metering: sabha_workers.relay).
- POST /v1/reanalysis {type, reason, rubric_id?, dry_run, limit} (Idempotency-Key): owners and admins. The
  finished recordings of a type whose latest analysis used another rubric than the target (the tenant's current
  default, or the one given), oldest first. dry_run only counts; otherwise at most `limit` (<= 100) start, each as
  above, and the rest are reported as remaining for another request. Running ones are not COMPLETED, so they are
  never counted twice.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import BadRequestError, ConflictError, ForbiddenError
from sabha_api.services.recordings import AsrModelUnavailableError, TransferNotAllowedError
from sabha_api.services.results import visible_recording
from sabha_asr.registry import AsrConfigError, chosen_spec
from sabha_core.models import (
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
    TRANSFERRED_SPEAKERS,
    Analysis,
    AuditEntry,
    Dispute,
    OutboxEvent,
    Person,
    Recording,
    SpeakerModel,
    Tenant,
    Transcript,
    utc_now,
)
from sabha_core.outbox import record_transition_async
from sabha_core.profiles import ConversationType, get_profile
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.state import ConcurrentTransition, RecordingStatus

ROUTE = "POST /v1/recordings/{recording_id}/reanalyze"
BULK_ROUTE = "POST /v1/reanalysis"
ALLOWED = frozenset({Role.OWNER, Role.ADMIN})
MAX_BULK = 100
CLOSED_NOTE = "Re-analysed"
_RUBRIC_ID = re.compile(r"^(?P<type>[a-z]+)\.[a-z][a-z0-9_]*\.v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class NotCompletedError(ConflictError):
    code, title = "not_completed", "Only a finished recording can be re-analysed"


class NoTranscriptError(ConflictError):
    code, title = "no_transcript", "This recording has no transcript to re-analyse"


class UnknownRubricError(BadRequestError):
    code, title = "unknown_rubric", "Unknown rubric"


class SpeechIn(BaseModel):
    """Transcribe again with these models before scoring (ADR 0018); the same choices as at upload."""

    model_config = ConfigDict(extra="forbid")

    asr_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = Field(
        default=None, description="'provider:model' from GET /v1/speech-models; left out, the configured model"
    )
    speaker_count: int | None = Field(default=None, ge=SPEAKER_COUNT_MIN, le=SPEAKER_COUNT_MAX)
    speaker_model: SpeakerModel = "pyannote"


class ReanalyzeIn(BaseModel):
    reason: Reason
    rubric_id: str | None = Field(default=None, description="Another rubric version of the same type")
    speech: SpeechIn | None = Field(
        default=None, description="Transcribe again with other models; left out, scores only"
    )


class NoAudioError(ConflictError):
    code, title = "no_audio", "There is no audio to transcribe again"


class ReanalyzeOut(BaseModel):
    recording_id: str
    status: str
    analysis_run: int


class BulkIn(BaseModel):
    type: ConversationType
    reason: Reason
    rubric_id: str | None = Field(default=None, description="The rubric to bring them to; the current one if empty")
    dry_run: bool = Field(default=False, description="Only count")
    limit: int = Field(default=MAX_BULK, ge=1, le=MAX_BULK)


class BulkOut(BaseModel):
    rubric_id: str
    matching: int  # finished recordings of the type scored with another rubric
    started: int
    remaining: int


def require_allowed(principal: Principal) -> None:
    if principal.role not in ALLOWED:
        raise ForbiddenError("Only owners and administrators re-analyse recordings.")


def check_rubric(rubric_id: str, conversation_type: ConversationType, rubrics_dir: str) -> str:
    match = _RUBRIC_ID.match(rubric_id)
    if match is None or match["type"] != conversation_type.value:
        raise UnknownRubricError(f"{rubric_id!r} is not a rubric for {conversation_type.value} recordings.")
    if not (Path(rubrics_dir) / f"{rubric_id}.yaml").is_file():
        raise UnknownRubricError(f"There is no rubric {rubric_id}.")
    return rubric_id


async def _start(
    principal: Principal, recording: Recording, reason: str, rubric_id: str | None, request: Request, *,
    recordings: TenantRepo[Recording], disputes: TenantRepo[Dispute], outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry], transactions: Transactions, redo: SpeechRedo | None = None,
) -> ReanalyzeOut:  # fmt: skip
    run = recording.analysis_run + 1
    meta: dict[str, Any] = {"reanalysis": True, "analysis_run": run, "reason": reason, "rubric_id": rubric_id}
    target, fields = RecordingStatus.ANALYZING, {"analysis_run": run, "rubric_id": rubric_id}
    if redo is not None:
        target, fields = redo.target, fields | redo.fields
        meta |= redo.meta
    closed = {"status": "closed", "resolution_note": CLOSED_NOTE, "resolved_by": principal.user_id,
              "resolved_by_role": principal.role.value, "resolved_at": utc_now()}  # fmt: skip
    try:
        async with transactions.run() as session:
            await recordings.update_one({"_id": recording.id, "status": RecordingStatus.COMPLETED.value},
                                        {"$set": fields}, session=session)  # fmt: skip
            await record_transition_async(recordings, outbox, recording.id, RecordingStatus.COMPLETED, target,
                                          reason="reanalysis", meta=meta, reanalysis=True,
                                          session=session)  # fmt: skip
            await disputes.update_many({"recording_id": recording.id, "status": "open"}, {"$set": closed},
                                       session=session)  # fmt: skip
            await audit(entries, principal, request, action="recording.reanalyze", target_type="recording",
                        target_id=recording.id, meta=meta, session=session)  # fmt: skip
    except ConcurrentTransition as exc:
        raise NotCompletedError("This recording is no longer finished: it may be re-analysing already.") from exc
    return ReanalyzeOut(recording_id=recording.id, status=target.value, analysis_run=run)


class SpeechRedo(BaseModel):
    """Where a re-analysis with other speech models starts, and what changes on the recording (ADR 0018)."""

    target: RecordingStatus
    fields: dict[str, Any]
    meta: dict[str, Any]


def speech_redo(recording: Recording, speech: SpeechIn, settings: Settings) -> SpeechRedo:
    """Check a request to transcribe again and work out its start: speaker separation again when the number of
    speakers changes (its labels change, so confirmed roles and voice names no longer fit), else transcription."""
    if recording.source != "audio" or recording.audio_deleted_at is not None:
        raise NoAudioError("This recording's audio is not kept any more, so it can only be scored again.")
    if recording.transferred and speech.speaker_count not in (None, TRANSFERRED_SPEAKERS):
        raise TransferNotAllowedError("A call a colleague helped on has three speakers: two agents and the customer.")
    asr_choice = None
    if speech.asr_model is not None:
        try:
            asr_choice = chosen_spec(speech.asr_model, settings)
        except AsrConfigError as exc:
            raise AsrModelUnavailableError(str(exc)) from exc
    fields: dict[str, Any] = {
        "asr_choice": asr_choice,
        "speaker_count": speech.speaker_count,
        "speaker_model": speech.speaker_model,
        "speech_run": recording.speech_run + 1,
    }
    target = RecordingStatus.TRANSCRIBING
    if speech.speaker_count != recording.speaker_count:
        target = RecordingStatus.DIARIZING
        fields |= {"diarize_run": recording.diarize_run + 1, "confirmed_roles": None, "voice_names": {}}
    meta = {"speech": {"asr_model": asr_choice, "speaker_count": speech.speaker_count,
                       "speaker_model": speech.speaker_model, "from": target.value}}  # fmt: skip
    return SpeechRedo(target=target, fields=fields, meta=meta)


async def reanalyze(
    principal: Principal, recording_id: str, body: ReanalyzeIn, request: Request, *, rubrics_dir: str,
    recordings: TenantRepo[Recording], people: TenantRepo[Person], transcripts: TenantRepo[Transcript],
    disputes: TenantRepo[Dispute], outbox: TenantRepo[OutboxEvent], entries: TenantRepo[AuditEntry],
    transactions: Transactions, settings: Settings | None = None,
) -> ReanalyzeOut:  # fmt: skip
    recording = await visible_recording(principal, recording_id, recordings, people)
    require_allowed(principal)
    if recording.status is not RecordingStatus.COMPLETED:
        raise NotCompletedError("Only a finished recording can be re-analysed.")
    rubric_id = None if body.rubric_id is None else check_rubric(body.rubric_id, recording.type, rubrics_dir)
    redo = None
    if body.speech is not None:
        if settings is None:  # pragma: no cover - the router always passes them
            raise RuntimeError("settings are needed to transcribe again")
        redo = speech_redo(recording, body.speech, settings)
    elif await transcripts.find_one({"recording_id": recording.id}) is None:
        raise NoTranscriptError("This recording has no transcript to score again.")
    return await _start(principal, recording, body.reason, rubric_id, request, recordings=recordings,
                        disputes=disputes, outbox=outbox, entries=entries, transactions=transactions,
                        redo=redo)  # fmt: skip


async def reanalyze_many(
    principal: Principal, body: BulkIn, request: Request, *, tenant: Tenant | None, rubrics_dir: str,
    recordings: TenantRepo[Recording], analyses: TenantRepo[Analysis], transcripts: TenantRepo[Transcript],
    disputes: TenantRepo[Dispute], outbox: TenantRepo[OutboxEvent], entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> BulkOut:  # fmt: skip
    require_allowed(principal)
    target = body.rubric_id
    if target is None and tenant is not None:
        target = get_profile(tenant.profile).default_rubrics.get(body.type)
    if target is None:
        raise UnknownRubricError(f"There is no rubric for {body.type.value} recordings.")
    target = check_rubric(target, body.type, rubrics_dir)

    finished = await recordings.find({"type": body.type.value, "status": RecordingStatus.COMPLETED.value},
                                     sort=[("created_at", 1), ("_id", 1)])  # fmt: skip
    latest = await analyses.find({"recording_id": {"$in": [r.id for r in finished]}, "superseded": {"$ne": True}})
    rubric_of = {a.recording_id: a.rubric_id for a in latest}
    with_transcript = {t.recording_id for t in await transcripts.find({"recording_id": {"$in": [r.id for r in
                       finished]}})}  # fmt: skip
    matching = [r for r in finished if rubric_of.get(r.id, target) != target and r.id in with_transcript]
    started = 0
    if not body.dry_run:
        for recording in matching[: body.limit]:
            await _start(principal, recording, body.reason, body.rubric_id and target, request,
                         recordings=recordings, disputes=disputes, outbox=outbox, entries=entries,
                         transactions=transactions)  # fmt: skip
            started += 1
    return BulkOut(rubric_id=target, matching=len(matching), started=started, remaining=len(matching) - started)
