"""Reviews (ADR 0007): recordings that need a person's decision, and the two outcomes.

- GET /v1/reviews: the NEEDS_REVIEW recordings the caller may see (the recordings list's rules), newest first,
  cursor paging. Owners, admins, managers and reviewers only: staff never resolve their own recordings (403).
- GET /v1/recordings/{id}/speakers: each speaker of the transcript with their talk time, Sabha's best guess and a
  few sample lines (ORIGINAL timeline), and the rubric's two roles to choose between, staff first.
- POST /v1/recordings/{id}/review:
  - {"action": "confirm_roles", "staff_speaker": "S1"}: only for `unclear_roles`. That speaker gets the staff role
    and every other speaker the other role (as the heuristics would have); the roles are stored on the recording
    and it moves NEEDS_REVIEW -> TRANSCRIBING, so the transcript is rebuilt with them and then scored. The speech
    recognition already done is reused (the transcribe stage's checkpoints), so nothing is billed twice.
  - {"action": "close", "note": "..."}: any reason. NEEDS_REVIEW -> FAILED with reason `closed_by_reviewer`.
  Each outcome is one transaction with its outbox event, and is audited (`recording.review`, with the decision).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import Request
from pydantic import BaseModel, Field, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from sabha_api.services.results import ArtefactReader, RecordingPage, list_recordings, visible_recording
from sabha_core.models import Analysis, AuditEntry, OutboxEvent, Person, Recording, Transcript
from sabha_core.outbox import record_transition_async
from sabha_core.repo import TenantRepo
from sabha_core.state import ConcurrentTransition, RecordingStatus

RESOLVERS = frozenset({Role.OWNER, Role.ADMIN, Role.MANAGER, Role.REVIEWER})
UNCLEAR_ROLES = "unclear_roles"
CLOSED = "closed_by_reviewer"
SAMPLES = 3
SAMPLE_CHARS = 240


class NotInReviewError(ConflictError):
    code, title = "not_in_review", "Not waiting for review"


class NotARolesReviewError(ConflictError):
    code, title = "not_a_roles_review", "Not a question of roles"


class UnknownSpeakerError(BadRequestError):
    code, title = "unknown_speaker", "Unknown speaker"


def require_resolver(principal: Principal) -> None:
    if principal.role not in RESOLVERS:
        raise ForbiddenError("Only reviewers, managers and administrators handle reviews.")


async def review_queue(
    principal: Principal, *, cursor: str | None, limit: int, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], analyses: TenantRepo[Analysis],
) -> RecordingPage:  # fmt: skip
    require_resolver(principal)
    return await list_recordings(principal, cursor=cursor, limit=limit, recordings=recordings, people=people,
                                 analyses=analyses, status=RecordingStatus.NEEDS_REVIEW)  # fmt: skip


class Sample(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class Speaker(BaseModel):
    label: str  # as diarization named them: "S0", "S1"
    guess: str | None  # Sabha's best guess at their role, which the reviewer is asked to check
    talk_ms: int
    share: float  # of all speech, 0 to 1
    samples: list[Sample]  # the longest turns, in time order


class SpeakersOut(BaseModel):
    recording_id: str
    reason: str | None
    choices: list[str]  # the rubric's two roles, staff first
    speakers: list[Speaker]  # most talk first


def _clip(text: str) -> str:
    return text if len(text) <= SAMPLE_CHARS else text[: SAMPLE_CHARS - 1].rstrip() + "…"


async def speakers(
    principal: Principal, recording_id: str, *, recordings: TenantRepo[Recording], people: TenantRepo[Person],
    transcripts: TenantRepo[Transcript], reader: ArtefactReader,
) -> SpeakersOut:  # fmt: skip
    require_resolver(principal)
    recording = await visible_recording(principal, recording_id, recordings, people)
    doc = await transcripts.find_one({"recording_id": recording.id})
    content = None if doc is None else await reader.json(doc.storage_key)
    if doc is None or content is None:
        raise NotFoundError("This recording has no transcript yet.")
    turns: dict[str, list[dict[str, Any]]] = {}
    for utterance in content["utterances"]:
        turns.setdefault(utterance["speaker_label"], []).append(utterance)
    talk = {label: sum(u["end_ms"] - u["start_ms"] for u in mine) for label, mine in turns.items()}
    total = sum(talk.values()) or 1
    out = []
    for label in sorted(turns, key=lambda name: (-talk[name], name)):
        longest = sorted(turns[label], key=lambda u: u["end_ms"] - u["start_ms"], reverse=True)[:SAMPLES]
        samples = [Sample(start_ms=u["start_ms"], end_ms=u["end_ms"], text=_clip(u["text"]))
                   for u in sorted(longest, key=lambda u: u["start_ms"])]  # fmt: skip
        out.append(Speaker(label=label, guess=doc.roles.get(label), talk_ms=talk[label],
                           share=round(talk[label] / total, 4), samples=samples))  # fmt: skip
    choices = doc.role_choices or sorted(set(doc.roles.values()))  # older transcripts did not store the choices
    return SpeakersOut(recording_id=recording.id, reason=recording.status_reason, choices=choices, speakers=out)


class ReviewIn(BaseModel):
    action: Literal["confirm_roles", "close"]
    staff_speaker: str | None = Field(default=None, description="confirm_roles: the speaker who is the staff member")
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = Field(
        default=None, description="close: why the recording is not usable (required)"
    )


class ReviewOut(BaseModel):
    recording_id: str
    status: str


async def resolve(
    principal: Principal, recording_id: str, body: ReviewIn, request: Request, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], transcripts: TenantRepo[Transcript], outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> ReviewOut:  # fmt: skip
    require_resolver(principal)
    recording = await visible_recording(principal, recording_id, recordings, people)
    if recording.status is not RecordingStatus.NEEDS_REVIEW:
        raise NotInReviewError("This recording is not waiting for review.")

    if body.action == "close":
        if not body.note:
            raise BadRequestError("Say why the recording is not usable.")
        target, reason, update = RecordingStatus.FAILED, CLOSED, None
        meta: dict[str, Any] = {"decision": "close", "note": body.note, "review_reason": recording.status_reason}
    else:
        if recording.status_reason != UNCLEAR_ROLES:
            raise NotARolesReviewError("Only a recording whose speakers were unclear can have its roles confirmed.")
        doc = await transcripts.find_one({"recording_id": recording.id})
        if doc is None or len(doc.role_choices or set(doc.roles.values())) < 2:
            raise NotFoundError("This recording has no transcript with roles to confirm.")
        if body.staff_speaker not in doc.roles:
            raise UnknownSpeakerError(f"{body.staff_speaker!r} is not one of this recording's speakers.")
        staff_role, other_role = (doc.role_choices or sorted(set(doc.roles.values())))[:2]
        roles = {label: staff_role if label == body.staff_speaker else other_role for label in doc.roles}
        target, reason, update = RecordingStatus.TRANSCRIBING, "roles_confirmed", {"confirmed_roles": roles}
        meta = {"decision": "confirm_roles", "roles": roles}

    try:
        async with transactions.run() as session:
            if update is not None:
                await recordings.update_one({"_id": recording.id}, {"$set": update}, session=session)
            await record_transition_async(recordings, outbox, recording.id, RecordingStatus.NEEDS_REVIEW, target,
                                          reason=reason, meta=meta, review=True, session=session)  # fmt: skip
            await audit(entries, principal, request, action="recording.review", target_type="recording",
                        target_id=recording.id, meta=meta, session=session)  # fmt: skip
    except ConcurrentTransition as exc:
        raise NotInReviewError("Someone else resolved this recording first.") from exc
    return ReviewOut(recording_id=recording.id, status=target.value)
