"""Sharing a report with the person analysed (UI v2 "Share with Anjali" and "Share with staff"; owner's decision
2026-11-03).

Sharing does not change who may see a report: the person analysed already sees their own. It records that a manager
sent it (shared_at, shared_by and an optional note shown on the person's report), writes recording.shared to the
outbox so the notify step emails the person, and audits recording.share. The email carries no note, score or quote
(sabha_workers.notifications.emails), only a link.

Who may share: anyone who can see the recording except staff (owners and admins for every recording, managers and
reviewers for their units). Only a completed recording with a person analysed can be shared. Sharing again replaces
the note and sends another email.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Request
from pydantic import BaseModel, Field, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ForbiddenError
from sabha_api.services.results import visible_filter
from sabha_core.models import AuditEntry, OutboxEvent, Person, Recording, utc_now
from sabha_core.outbox import record_event_async
from sabha_core.repo import TenantRepo
from sabha_core.state import RecordingStatus

SHARE_ROUTE = "POST /v1/recordings/share"
SHARED_EVENT = "recording.shared"
MAX_SHARE = 100

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ShareIn(BaseModel):
    recording_ids: list[str] = Field(min_length=1, max_length=MAX_SHARE)
    note: Note | None = None


class ShareOut(BaseModel):
    shared: list[str]
    # Visible but not shareable: not completed yet, or nobody analysed (a meeting). Ids the caller cannot see are
    # left out of both lists, as if they did not exist.
    skipped: list[str]


async def share(
    principal: Principal, body: ShareIn, request: Request, *, recordings: TenantRepo[Recording],
    people: TenantRepo[Person], outbox: TenantRepo[OutboxEvent], entries: TenantRepo[AuditEntry],
    transactions: Transactions,
) -> ShareOut:  # fmt: skip
    if principal.role is Role.STAFF:
        raise ForbiddenError("Only managers, reviewers and administrators can share a report.")
    ids = list(dict.fromkeys(body.recording_ids))
    visible = await visible_filter(principal, people)
    found = await recordings.find({"$and": [c for c in (visible, {"_id": {"$in": ids}}) if c]})
    ready = [r for r in found if r.status is RecordingStatus.COMPLETED and r.person_id]
    note = body.note or None
    now = utc_now()
    async with transactions.run() as session:
        for recording in ready:
            await recordings.update_one(
                {"_id": recording.id},
                {"$set": {"shared_at": now, "shared_by": principal.user_id, "share_note": note}},
                session=session,
            )
            event = {"recording_id": recording.id, "shared_by": principal.user_id}
            await record_event_async(outbox, SHARED_EVENT, event, session=session)
            await audit(entries, principal, request, action="recording.share", target_type="recording",
                        target_id=recording.id, session=session, meta={"with_note": note is not None})  # fmt: skip
    shared = {r.id for r in ready}
    return ShareOut(shared=[i for i in ids if i in shared],
                    skipped=[r.id for r in found if r.id not in shared])  # fmt: skip
