"""Recording status state machine: the ONLY place recording status transitions are defined (CLAUDE.md).

    CREATED -> UPLOADED -> PREPROCESSING -> DIARIZING -> TRANSCRIBING -> ANALYZING -> COMPLETED

Each worker stage (PREPROCESSING, DIARIZING, TRANSCRIBING, ANALYZING) can also move to FAILED or NEEDS_REVIEW.
COMPLETED -> ANALYZING is allowed only for re-analysis, and only when the caller says so (`reanalysis=True`).
Nothing leaves FAILED or NEEDS_REVIEW: retries and review outcomes are not defined yet, so they are not here.

This module is the pure part of plan task P2.3: the table and `check_transition`. `transition(session, ...)`,
which makes the conditional MongoDB update and returns the outbox event, and the stage_runs collection arrive with
P2.3's database part, once the tenant-scoped repository (P1.6) exists. That is also where golden rule 9 (no
consent_ref, no move past UPLOADED) belongs, because checking it needs the recording document.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


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


class TransitionError(Exception):
    """A recording's status change was refused."""


class InvalidTransition(TransitionError):
    """The transition table does not allow this change of status."""

    def __init__(self, from_status: RecordingStatus, to_status: RecordingStatus, message: str) -> None:
        super().__init__(message)
        self.from_status = from_status
        self.to_status = to_status


class ConcurrentTransition(TransitionError):
    """The recording was no longer in the expected status when the conditional update ran; another worker won.

    Raised by `transition()` once P2.3's database part lands.
    """


def next_statuses(from_status: RecordingStatus | str, *, reanalysis: bool = False) -> frozenset[RecordingStatus]:
    """The statuses a recording may move to from `from_status`. Raises ValueError for an unknown status."""
    source = RecordingStatus(from_status)
    allowed = ALLOWED_TRANSITIONS[source]
    if reanalysis:
        allowed = allowed | {target for start, target in REANALYSIS_TRANSITIONS if start is source}
    return allowed


def check_transition(
    from_status: RecordingStatus | str, to_status: RecordingStatus | str, *, reanalysis: bool = False
) -> None:
    """Raise InvalidTransition unless the table allows `from_status -> to_status`; otherwise return None.

    `reanalysis=True` allows COMPLETED -> ANALYZING and nothing else. Plain strings (as stored in MongoDB) are
    accepted; an unknown status raises ValueError.
    """
    source, target = RecordingStatus(from_status), RecordingStatus(to_status)
    allowed = next_statuses(source, reanalysis=reanalysis)
    if target in allowed:
        return
    if (source, target) in REANALYSIS_TRANSITIONS:
        message = f"{source} -> {target} is allowed only for re-analysis (reanalysis=True)"
    elif not allowed:
        message = f"cannot move a recording from {source} to {target}: there are no transitions out of {source}"
        if any(start is source for start, _ in REANALYSIS_TRANSITIONS):
            message += " except re-analysis (reanalysis=True)"
    else:
        names = ", ".join(status for status in RecordingStatus if status in allowed)
        message = f"cannot move a recording from {source} to {target}; allowed next: {names}"
    raise InvalidTransition(source, target, message)
