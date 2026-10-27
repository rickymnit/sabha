"""Retrying or closing a failed recording (plan task P7.8; owner's decision 2026-10-27: the tenant's owners and
admins, in the app, audited).

A recording is retryable when it is FAILED and has an open dead letter: one the stage runner wrote when a stage
failed for good (sabha_workers.stages.runner), not yet retried or closed. A recording a reviewer closed as not
usable (NEEDS_REVIEW -> FAILED) has none, so it stays closed.

- POST /v1/recordings/{id}/retry {reason}: one transaction moves the recording back to where the failed stage
  starts (sabha_core.state.retry_status, retry=True) with its outbox event, so the relay starts that stage again
  (preprocessing through the upload's "ready" event); marks the dead letter replayed; and writes recording.retry
  to the audit log. Earlier stages are not repeated: their artefacts exist (golden rule 3).
- POST /v1/recordings/{id}/abandon {reason}: the recording stays FAILED; the dead letter is marked abandoned, so it
  cannot be retried; recording.abandon is audited.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Request
from pydantic import BaseModel, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ConflictError, ForbiddenError
from sabha_api.services.results import visible_recording
from sabha_core.models import AuditEntry, DeadLetter, OutboxEvent, Person, Recording, utc_now
from sabha_core.outbox import record_transition_async
from sabha_core.repo import TenantRepo
from sabha_core.state import ConcurrentTransition, RecordingStatus, retry_status

RETRY_ROUTE = "POST /v1/recordings/{recording_id}/retry"
ABANDON_ROUTE = "POST /v1/recordings/{recording_id}/abandon"
ALLOWED = frozenset({Role.OWNER, Role.ADMIN})

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class NotFailedError(ConflictError):
    code, title = "not_failed", "Only a failed recording can be retried or closed"


class NotRetryableError(ConflictError):
    code, title = "not_retryable", "This recording cannot be retried"


class ReasonIn(BaseModel):
    reason: Reason


class RetryOut(BaseModel):
    recording_id: str
    status: str
    stage: str


async def _failed(
    principal: Principal, recording_id: str, recordings: TenantRepo[Recording], people: TenantRepo[Person],
    dlq: TenantRepo[DeadLetter],
) -> tuple[Recording, DeadLetter]:  # fmt: skip
    if principal.role not in ALLOWED:
        raise ForbiddenError("Only owners and administrators can retry or close a failed recording.")
    recording = await visible_recording(principal, recording_id, recordings, people)
    if recording.status is not RecordingStatus.FAILED:
        raise NotFailedError(f"This recording is {recording.status.lower().replace('_', ' ')}, not failed.")
    letters = await dlq.find({"recording_id": recording.id, "replayed_at": None, "abandoned_at": None},
                             sort=[("created_at", -1)], limit=1)  # fmt: skip
    if not letters:
        raise NotRetryableError("This recording was closed, by a reviewer or an administrator, and cannot be retried.")
    return recording, letters[0]


def _details(body: ReasonIn, letter: DeadLetter) -> dict[str, Any]:
    """What the audit entry records: why, and what had failed."""
    return {"reason": body.reason, "stage": letter.stage, "error_code": letter.error_code}


async def _mark(dlq: TenantRepo[DeadLetter], letter: DeadLetter, field: str, session: Any) -> None:
    matched = await dlq.update_one({"_id": letter.id, "replayed_at": None, "abandoned_at": None},
                                   {"$set": {field: utc_now()}}, session=session)  # fmt: skip
    if matched != 1:  # someone else retried or closed it at the same moment
        raise NotRetryableError("Someone has just retried or closed this recording.")


async def retry(
    principal: Principal, recording_id: str, body: ReasonIn, request: Request, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], dlq: TenantRepo[DeadLetter], outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> RetryOut:  # fmt: skip
    recording, letter = await _failed(principal, recording_id, recordings, people, dlq)
    target = retry_status(letter.stage)
    meta: dict[str, Any] = {"retry": True, "stage": letter.stage}
    if target is RecordingStatus.UPLOADED:
        meta["ready"] = True  # starts preprocessing (sabha_workers.relay.routes)
    try:
        async with transactions.run() as session:
            await record_transition_async(recordings, outbox, recording.id, RecordingStatus.FAILED, target,
                                          session=session, reason="retried", meta=meta, retry=True)  # fmt: skip
            await _mark(dlq, letter, "replayed_at", session)
            await audit(entries, principal, request, action="recording.retry", target_type="recording",
                        target_id=recording.id, session=session,
                        meta=_details(body, letter))  # fmt: skip
    except ConcurrentTransition as exc:
        raise NotFailedError("This recording has just been retried.") from exc
    return RetryOut(recording_id=recording.id, status=target.value, stage=letter.stage)


async def abandon(
    principal: Principal, recording_id: str, body: ReasonIn, request: Request, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], dlq: TenantRepo[DeadLetter], entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> RetryOut:  # fmt: skip
    recording, letter = await _failed(principal, recording_id, recordings, people, dlq)
    async with transactions.run() as session:
        await _mark(dlq, letter, "abandoned_at", session)
        await audit(entries, principal, request, action="recording.abandon", target_type="recording",
                    target_id=recording.id, session=session,
                    meta=_details(body, letter))  # fmt: skip
    return RetryOut(recording_id=recording.id, status=RecordingStatus.FAILED.value, stage=letter.stage)
