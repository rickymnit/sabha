"""The signed-in person's own workspace (founder's Sales Executive dashboard doc, 2026-11-12).

Every route here is about the caller's OWN person (the one linked to their user), whatever their role: a user with
no linked person gets empty lists. Nothing here shows anyone else's data, so these routes need no unit checks.

- next actions: the agreed next step of each of the person's finished sales calls and meetings from the last
  NEXT_ACTION_DAYS days (latest analysis of each, verified items only), with the client, the date as said, the date
  it means (sabha_analytics.follow_up.resolve_due, counted from the day of the conversation) and a priority from the
  rule in the tenant's current sales rubric (`follow_up`). The interest words come from the same rubric.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from sabha_analytics.follow_up import Priority, priority, resolve_due
from sabha_analytics.rubric import FollowUpRules, Rubric
from sabha_api.auth import Principal
from sabha_api.services.results import interaction_of, recording_title
from sabha_core.models import Analysis, Person, Recording, utc_now
from sabha_core.repo import TenantRepo

NEXT_ACTION_DAYS = 60
IST = timedelta(hours=5, minutes=30)
DEFAULT_RULE = FollowUpRules(high_interest=("high",), high_within_days=2, medium_within_days=7)
"""Used only if the tenant's sales rubric has no follow_up rule (older rubrics); the same as sales v0.4's."""
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class NextAction(BaseModel):
    recording_id: str
    title: str
    interaction: Literal["call", "meeting"] | None
    client: str | None  # as typed at upload, else as said in the conversation
    recorded_at: datetime
    action: str
    owner: str | None  # sales_rep, customer or both
    due_said: str | None  # exactly as said
    due_date: date | None  # what it means, when that is unambiguous
    overdue: bool
    priority: Priority
    interest: str | None  # the rubric's value, e.g. "high"
    interest_label: str | None  # the words users see, e.g. "Interested"


class NextActionList(BaseModel):
    items: list[NextAction]


def ist_day(moment: datetime) -> date:
    return (moment + IST).date()


async def own_person(principal: Principal, people: TenantRepo[Person]) -> Person | None:
    return await people.find_one({"user_id": principal.user_id})


async def next_actions(
    principal: Principal, *, people: TenantRepo[Person], recordings: TenantRepo[Recording],
    analyses: TenantRepo[Analysis], rubric: Rubric | None, now: datetime | None = None,
) -> NextActionList:  # fmt: skip
    person = await own_person(principal, people)
    if person is None:
        return NextActionList(items=[])
    now = now or utc_now()
    found = await analyses.find(
        {"person_id": person.id, "conversation_type": "sales", "status": "COMPLETED", "superseded": {"$ne": True},
         "next_action": {"$ne": None}, "created_at": {"$gte": now - timedelta(days=NEXT_ACTION_DAYS)}},
        sort=[("created_at", -1)], limit=200,
    )  # fmt: skip
    by_id = {r.id: r for r in await recordings.find({"_id": {"$in": [a.recording_id for a in found]}})}
    rule = (rubric.follow_up if rubric is not None else None) or DEFAULT_RULE
    labels = dict((rubric.output_labels or {}).get("interest_level", {})) if rubric is not None else {}
    today = ist_day(now)
    items = []
    for analysis in found:
        recording = by_id.get(analysis.recording_id)
        if recording is None or analysis.next_action is None:
            continue
        spoken = recording.recorded_at or recording.created_at
        due = resolve_due(analysis.next_action_due, ist_day(spoken))
        items.append(NextAction(
            recording_id=recording.id, title=recording_title(recording.file_name, recording.id),
            interaction=interaction_of(recording), client=recording.client_name or analysis.client_said,
            recorded_at=spoken, action=analysis.next_action, owner=analysis.next_action_owner,
            due_said=analysis.next_action_due, due_date=due, overdue=due is not None and due < today,
            priority=priority(rule, interest=analysis.interest_level, due=due, today=today),
            interest=analysis.interest_level,
            interest_label=labels.get(analysis.interest_level) if analysis.interest_level else None,
        ))  # fmt: skip
    items.sort(key=lambda a: (PRIORITY_ORDER[a.priority], a.due_date or date.max, -a.recorded_at.timestamp()))
    return NextActionList(items=items)
