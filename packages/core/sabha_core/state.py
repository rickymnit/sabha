"""Recording status state machine: the ONLY place recording status transitions are defined (CLAUDE.md).

    CREATED -> UPLOADED -> PREPROCESSING -> DIARIZING -> TRANSCRIBING -> ANALYZING -> COMPLETED

Each worker stage (PREPROCESSING, DIARIZING, TRANSCRIBING, ANALYZING) can also move to FAILED or NEEDS_REVIEW.
COMPLETED -> ANALYZING is allowed only for re-analysis, and only when the caller says so (`reanalysis=True`).
NEEDS_REVIEW has two ways out, both a reviewer's decision and allowed only with `review=True` (ADR 0007):
NEEDS_REVIEW -> TRANSCRIBING once the speaker roles are confirmed (the transcript is rebuilt with them, then
scored), and NEEDS_REVIEW -> FAILED when the reviewer closes the recording as not usable. Nothing leaves FAILED:
retries are not defined yet.

`transition()` (sync, for workers) and `transition_async()` (for the API) apply a change through the
tenant-scoped repository with a conditional update: the recording must still be in `from_status`, so of two
workers racing, one wins and the other gets ConcurrentTransition. They enforce golden rule 9 in the same update: a
recording without a consent_ref cannot move past UPLOADED (ConsentRequired). They return the outbox event
describing the change, `recording.<new status>`; the caller writes it in the same transaction (P2.5). Pass the
transaction's session.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # models import RecordingStatus from here, so these are imported where they are used
    from pymongo.asynchronous.client_session import AsyncClientSession
    from pymongo.client_session import ClientSession

    from sabha_core.models import OutboxEvent, Recording
    from sabha_core.repo import SyncTenantRepo, TenantRepo


class RecordingStatus(StrEnum):
    """Where a recording is in the pipeline. Stored in MongoDB as the plain upper-case string."""

    CREATED = "CREATED"
    UPLOADED = "UPLOADED"
    PREPROCESSING = "PREPROCESSING"
    DIARIZING = "DIARIZING"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


_S = RecordingStatus

WORKER_STAGES: frozenset[RecordingStatus] = frozenset({_S.PREPROCESSING, _S.DIARIZING, _S.TRANSCRIBING, _S.ANALYZING})
"""Statuses in which a worker is processing the recording. Each can end in FAILED or NEEDS_REVIEW."""

TERMINAL_STATUSES: frozenset[RecordingStatus] = frozenset({_S.COMPLETED, _S.FAILED, _S.NEEDS_REVIEW})
"""Statuses in which the pipeline has stopped. Only re-analysis (COMPLETED -> ANALYZING) leaves one of them."""

ALLOWED_TRANSITIONS: Mapping[RecordingStatus, frozenset[RecordingStatus]] = MappingProxyType(
    {
        _S.CREATED: frozenset({_S.UPLOADED}),
        _S.UPLOADED: frozenset({_S.PREPROCESSING}),
        _S.PREPROCESSING: frozenset({_S.DIARIZING, _S.FAILED, _S.NEEDS_REVIEW}),
        _S.DIARIZING: frozenset({_S.TRANSCRIBING, _S.FAILED, _S.NEEDS_REVIEW}),
        _S.TRANSCRIBING: frozenset({_S.ANALYZING, _S.FAILED, _S.NEEDS_REVIEW}),
        _S.ANALYZING: frozenset({_S.COMPLETED, _S.FAILED, _S.NEEDS_REVIEW}),
        _S.COMPLETED: frozenset(),
        _S.FAILED: frozenset(),
        _S.NEEDS_REVIEW: frozenset(),
    }
)
"""Every transition allowed without flags, as {from: {to, ...}}. Read-only."""

REANALYSIS_TRANSITIONS: frozenset[tuple[RecordingStatus, RecordingStatus]] = frozenset({(_S.COMPLETED, _S.ANALYZING)})
"""Transitions allowed only for re-analysis (`reanalysis=True`), as (from, to) pairs."""

REVIEW_TRANSITIONS: frozenset[tuple[RecordingStatus, RecordingStatus]] = frozenset(
    {(_S.NEEDS_REVIEW, _S.TRANSCRIBING), (_S.NEEDS_REVIEW, _S.FAILED)}
)
"""A reviewer's outcomes (`review=True`): roles confirmed, or closed as not usable. As (from, to) pairs."""


class TransitionError(Exception):
    """A recording's status change was refused."""


class InvalidTransition(TransitionError):
    """The transition table does not allow this change of status."""

    def __init__(self, from_status: RecordingStatus, to_status: RecordingStatus, message: str) -> None:
        super().__init__(message)
        self.from_status = from_status
        self.to_status = to_status


class ConcurrentTransition(TransitionError):
    """The recording was no longer in the expected status when the conditional update ran; another worker won."""


class ConsentRequired(TransitionError):
    """Golden rule 9: a recording without a consent_ref cannot move past UPLOADED."""


class RecordingNotFound(TransitionError):
    """No recording with this id in the repository's tenant."""


def next_statuses(
    from_status: RecordingStatus | str, *, reanalysis: bool = False, review: bool = False
) -> frozenset[RecordingStatus]:
    """The statuses a recording may move to from `from_status`. Raises ValueError for an unknown status."""
    source = RecordingStatus(from_status)
    allowed = ALLOWED_TRANSITIONS[source]
    if reanalysis:
        allowed = allowed | {target for start, target in REANALYSIS_TRANSITIONS if start is source}
    if review:
        allowed = allowed | {target for start, target in REVIEW_TRANSITIONS if start is source}
    return allowed


def check_transition(
    from_status: RecordingStatus | str, to_status: RecordingStatus | str, *, reanalysis: bool = False,
    review: bool = False,
) -> None:  # fmt: skip
    """Raise InvalidTransition unless the table allows `from_status -> to_status`; otherwise return None.

    `reanalysis=True` allows COMPLETED -> ANALYZING and nothing else; `review=True` allows only REVIEW_TRANSITIONS.
    Plain strings (as stored in MongoDB) are accepted; an unknown status raises ValueError.
    """
    source, target = RecordingStatus(from_status), RecordingStatus(to_status)
    allowed = next_statuses(source, reanalysis=reanalysis, review=review)
    if target in allowed:
        return
    if (source, target) in REANALYSIS_TRANSITIONS:
        message = f"{source} -> {target} is allowed only for re-analysis (reanalysis=True)"
    elif (source, target) in REVIEW_TRANSITIONS:
        message = f"{source} -> {target} is allowed only as a review outcome (review=True)"
    elif not allowed:
        message = f"cannot move a recording from {source} to {target}: there are no transitions out of {source}"
        if any(start is source for start, _ in REANALYSIS_TRANSITIONS):
            message += " except re-analysis (reanalysis=True)"
        if any(start is source for start, _ in REVIEW_TRANSITIONS):
            message += " except a review outcome (review=True)"
    else:
        names = ", ".join(status for status in RecordingStatus if status in allowed)
        message = f"cannot move a recording from {source} to {target}; allowed next: {names}"
    raise InvalidTransition(source, target, message)


# --- Applying a transition (database part) ---

_NO_CONSENT_NEEDED = frozenset({_S.UPLOADED})  # an upload may complete before consent is recorded (P2.2)


def _plan(
    recording_id: str,
    from_status: RecordingStatus | str,
    to_status: RecordingStatus | str,
    *,
    tenant_id: str,
    reason: str,
    meta: Mapping[str, Any] | None,
    reanalysis: bool,
    review: bool,
    now: datetime | None,
) -> tuple[dict[str, Any], dict[str, Any], OutboxEvent]:
    from sabha_core.models import OutboxEvent, utc_now

    check_transition(from_status, to_status, reanalysis=reanalysis, review=review)
    source, target = RecordingStatus(from_status), RecordingStatus(to_status)
    at = now or utc_now()
    filter: dict[str, Any] = {"_id": recording_id, "status": source.value}
    if target not in _NO_CONSENT_NEEDED:
        filter["consent_ref"] = {"$type": "string", "$ne": ""}
    update = {"$set": {"status": target.value, "status_reason": reason, "status_changed_at": at}}
    event = OutboxEvent(
        tenant_id=tenant_id,
        type=f"recording.{target.lower()}",
        payload={
            "recording_id": recording_id,
            "from_status": source.value,
            "to_status": target.value,
            "reason": reason,
            "meta": dict(meta or {}),
        },
        created_at=at,
    )
    return filter, update, event


def _refusal(recording: Recording | None, recording_id: str, source: RecordingStatus) -> TransitionError:
    if recording is None:
        return RecordingNotFound(f"no recording {recording_id!r} in this tenant")
    if recording.status is not source:
        return ConcurrentTransition(f"recording {recording_id!r} is {recording.status}, not {source}")
    return ConsentRequired(f"recording {recording_id!r} has no consent_ref; it cannot move past UPLOADED")


def transition(
    recordings: SyncTenantRepo[Recording],
    recording_id: str,
    from_status: RecordingStatus | str,
    to_status: RecordingStatus | str,
    *,
    reason: str,
    meta: Mapping[str, Any] | None = None,
    reanalysis: bool = False,
    review: bool = False,
    session: ClientSession | None = None,
    now: datetime | None = None,
) -> OutboxEvent:
    """Move a recording from `from_status` to `to_status` and return the outbox event (not written).

    Raises InvalidTransition, ConcurrentTransition, ConsentRequired or RecordingNotFound; on any of them the
    recording is unchanged.
    """
    filter, update, event = _plan(
        recording_id, from_status, to_status,
        tenant_id=recordings.tenant_id, reason=reason, meta=meta, reanalysis=reanalysis, review=review, now=now,
    )  # fmt: skip
    if recordings.update_one(filter, update, session=session) == 1:
        return event
    current = recordings.find_one({"_id": recording_id}, session=session)
    raise _refusal(current, recording_id, RecordingStatus(from_status))


async def transition_async(
    recordings: TenantRepo[Recording],
    recording_id: str,
    from_status: RecordingStatus | str,
    to_status: RecordingStatus | str,
    *,
    reason: str,
    meta: Mapping[str, Any] | None = None,
    reanalysis: bool = False,
    review: bool = False,
    session: AsyncClientSession | None = None,
    now: datetime | None = None,
) -> OutboxEvent:
    """`transition` for the API's async repository."""
    filter, update, event = _plan(
        recording_id, from_status, to_status,
        tenant_id=recordings.tenant_id, reason=reason, meta=meta, reanalysis=reanalysis, review=review, now=now,
    )  # fmt: skip
    if await recordings.update_one(filter, update, session=session) == 1:
        return event
    current = await recordings.find_one({"_id": recording_id}, session=session)
    raise _refusal(current, recording_id, RecordingStatus(from_status))
