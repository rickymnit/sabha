"""GET /v1/inbox: what is waiting for the caller's decision (UI v2: the header bell and the Overview's "Needs your
decision"). Exactly these four kinds (owner's choice, 2026-10-27), each only where the caller may act on it:

- "dispute": an open dispute the caller may decide (reviewers, managers, owners, admins; their units, or all for
  owners and admins), never one they raised (P6.7);
- "review": a recording in NEEDS_REVIEW the caller may resolve (the same people; ADR 0007). `reason` says why, so
  the app can ask "who is the teacher?" for unclear_roles;
- "failed": a failed recording not yet retried or closed, for owners and admins (who may retry or close it, P7.8);
- "follow_up": a reception call from the last FOLLOW_UP_DAYS whose ticket says a follow-up is needed (only tickets
  with verified quotes are stored, golden rule 5), for anyone who may see the recording.

Nothing here is stored: the list is worked out on each call, so an item disappears as soon as it is dealt with. A
follow-up has no "done" yet, so it shows for FOLLOW_UP_DAYS after the call was analysed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from sabha_api.auth import Principal
from sabha_api.services.disputes import visible_disputes
from sabha_api.services.results import recording_title, status_note, visible_filter
from sabha_api.services.retry import ALLOWED as MAY_RETRY
from sabha_api.services.reviews import RESOLVERS
from sabha_core.models import Analysis, DeadLetter, Dispute, Person, Recording, Unit, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo
from sabha_core.state import RecordingStatus

FOLLOW_UP_DAYS = 7
PER_KIND = 25  # the bell shows a short list; the Reviews page has the full queues

Kind = Literal["dispute", "review", "failed", "follow_up"]


class InboxItem(BaseModel):
    kind: Kind
    id: str  # unique in the list: "<kind>:<dispute or recording id>"
    recording_id: str
    recording_title: str
    recording_type: str
    person_name: str | None
    unit: str | None
    at: datetime  # when it started waiting
    # dispute
    dispute_id: str | None = None
    dimension_name: str | None = None
    ai_score: int | None = None
    proposed_score: int | None = None
    # review and failed: the stored reason code and the same reason in plain words
    reason: str | None = None
    note: str | None = None
    # follow_up
    follow_up: str | None = None
    ticket_category: str | None = None


class InboxOut(BaseModel):
    items: list[InboxItem]  # newest first
    counts: dict[str, int]  # per kind, only kinds with items


async def inbox(
    principal: Principal, *, recordings: TenantRepo[Recording], people: TenantRepo[Person],
    analyses: TenantRepo[Analysis], disputes: TenantRepo[Dispute], dlq: TenantRepo[DeadLetter],
    units: TenantRepo[Unit],
) -> InboxOut:  # fmt: skip
    visible = await visible_filter(principal, people)
    waiting: list[tuple[Kind, Recording, datetime, dict[str, object]]] = []
    by_id: dict[str, Recording] = {}

    async def load(ids: list[str]) -> None:
        missing = [i for i in ids if i not in by_id]
        if missing:
            for r in await recordings.find({"$and": [visible, {"_id": {"$in": missing}}]}):
                by_id[r.id] = r

    if principal.role in RESOLVERS:
        found = await disputes.find({"$and": [c for c in (visible_disputes(principal), {"status": "open"}) if c]},
                                    sort=[("created_at", -1)], limit=PER_KIND + 10)  # fmt: skip
        found = [d for d in found if d.raised_by != principal.user_id][:PER_KIND]
        await load([d.recording_id for d in found])
        for d in found:
            if d.recording_id in by_id:
                waiting.append(("dispute", by_id[d.recording_id], d.created_at, {
                    "dispute_id": d.id, "dimension_name": d.dimension_name, "ai_score": d.ai_score,
                    "proposed_score": d.proposed_score, "id": f"dispute:{d.id}",
                }))  # fmt: skip
        for r in await recordings.find({"$and": [visible, {"status": RecordingStatus.NEEDS_REVIEW.value}]},
                                       sort=[("status_changed_at", -1)], limit=PER_KIND):  # fmt: skip
            waiting.append(("review", r, r.status_changed_at or r.created_at,
                            {"reason": r.status_reason, "note": status_note(r)}))  # fmt: skip

    if principal.role in MAY_RETRY:
        failed = await recordings.find({"$and": [visible, {"status": RecordingStatus.FAILED.value}]},
                                       sort=[("status_changed_at", -1)], limit=PER_KIND * 2)  # fmt: skip
        letters = await dlq.find({"recording_id": {"$in": [r.id for r in failed]}, "replayed_at": None,
                                  "abandoned_at": None})  # fmt: skip
        open_letters = {letter.recording_id for letter in letters}
        for r in [r for r in failed if r.id in open_letters][:PER_KIND]:
            waiting.append(("failed", r, r.status_changed_at or r.created_at,
                            {"reason": r.status_reason, "note": status_note(r)}))  # fmt: skip

    since = utc_now() - timedelta(days=FOLLOW_UP_DAYS)
    calls = await analyses.find({"conversation_type": ConversationType.RECEPTION.value, "superseded": False,
                                 "ticket_status": "follow_up_needed", "created_at": {"$gte": since}},
                                sort=[("created_at", -1)], limit=PER_KIND * 2)  # fmt: skip
    await load([a.recording_id for a in calls])
    for a in [a for a in calls if a.recording_id in by_id][:PER_KIND]:
        waiting.append(("follow_up", by_id[a.recording_id], a.created_at,
                        {"follow_up": a.ticket_follow_up, "ticket_category": a.ticket_category}))  # fmt: skip

    person_ids = sorted({r.person_id for _, r, _, _ in waiting if r.person_id})
    names = {p.id: p.name for p in await people.find({"_id": {"$in": person_ids}})} if person_ids else {}
    unit_ids = sorted({r.unit_id for _, r, _, _ in waiting if r.unit_id})
    unit_names = {u.id: u.name for u in await units.find({"_id": {"$in": unit_ids}})} if unit_ids else {}
    items = [
        InboxItem.model_validate({
            "kind": kind, "id": f"{kind}:{r.id}", "recording_id": r.id,
            "recording_title": recording_title(r.file_name, r.id), "recording_type": r.type.value,
            "person_name": names.get(r.person_id or ""), "unit": unit_names.get(r.unit_id or ""), "at": at, **extra,
        })
        for kind, r, at, extra in waiting
    ]  # fmt: skip
    items.sort(key=lambda item: item.at, reverse=True)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return InboxOut(items=items, counts=counts)
