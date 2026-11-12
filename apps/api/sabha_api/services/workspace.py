"""The signed-in person's own workspace (founder's Sales Executive dashboard doc, 2026-11-12).

Every route here is about the caller's OWN person (the one linked to their user), whatever their role: a user with
no linked person gets empty lists. Nothing here shows anyone else's data, so these routes need no unit checks.

- next actions: the agreed next step of each of the person's finished sales calls and meetings from the last
  NEXT_ACTION_DAYS days (latest analysis of each, verified items only), with the client, the date as said, the date
  it means (sabha_analytics.follow_up.resolve_due, counted from the day of the conversation) and a priority from the
  rule in the tenant's current sales rubric (`follow_up`). The interest words come from the same rubric.
- summary (Overview): the person's sales calls, meetings and both together in this week or month (Asia/Kolkata;
  weeks start on Monday) and the one before, and the average overall score of the finished ones in each. Failed
  recordings are not counted. Numbers only, computed here (golden rule 5).
- coaching: the person's average score per coaching theme (the rubric's `themes`, each the mean of the shown scores
  of its dimensions) over the last THEME_DAYS days and the THEME_DAYS before, the weakest theme as the focus, and
  their practice points, newest first (learning history). The practice points are private coaching: only these
  routes, for the person's own recordings, return them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from sabha_analytics.follow_up import Priority, priority, resolve_due
from sabha_analytics.rubric import FollowUpRules, Rubric
from sabha_api.auth import Principal
from sabha_api.services.results import interaction_of, recording_title
from sabha_core.models import Analysis, Person, Recording, Score, utc_now
from sabha_core.repo import TenantRepo

NEXT_ACTION_DAYS = 60
IST = timedelta(hours=5, minutes=30)
DEFAULT_RULE = FollowUpRules(high_interest=("high",), high_within_days=2, medium_within_days=7)
"""Used only if the tenant's sales rubric has no follow_up rule (older rubrics); the same as sales v0.4's."""
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
THEME_DAYS = 30
MAX_PRACTICE_POINTS = 30


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


# --- Summary (the Overview's numbers) ---


class PeriodCounts(BaseModel):
    start: date  # first day, Asia/Kolkata
    end: date  # last day
    calls: int
    meetings: int
    total: int
    score: float | None  # average overall score of the finished ones; None when none are scored
    scored: int


class Summary(BaseModel):
    period: Literal["week", "month"]
    current: PeriodCounts
    previous: PeriodCounts


def period_bounds(period: Literal["week", "month"], today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """(start, end) of the current week or month that holds `today`, and of the one before (inclusive days)."""
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return (start, start + timedelta(days=6)), (start - timedelta(days=7), start - timedelta(days=1))
    start = today.replace(day=1)
    following = (start + timedelta(days=32)).replace(day=1)
    previous_start = (start - timedelta(days=1)).replace(day=1)
    return (start, following - timedelta(days=1)), (previous_start, start - timedelta(days=1))


def _utc_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=utc_now().tzinfo) - IST


async def _counts(
    person: Person, span: tuple[date, date], *, recordings: TenantRepo[Recording], analyses: TenantRepo[Analysis]
) -> PeriodCounts:
    window = {"$gte": _utc_start(span[0]), "$lt": _utc_start(span[1] + timedelta(days=1))}
    found = await recordings.find({
        "person_id": person.id, "type": "sales", "status": {"$ne": "FAILED"},
        "$or": [{"recorded_at": window}, {"recorded_at": None, "created_at": window}],
    }, limit=5_000)  # fmt: skip
    calls = sum(1 for r in found if interaction_of(r) == "call")
    scored = await analyses.find({
        "recording_id": {"$in": [r.id for r in found]}, "status": "COMPLETED", "superseded": {"$ne": True},
        "overall_score": {"$ne": None},
    }, limit=5_000)  # fmt: skip
    values = [a.overall_score for a in scored if a.overall_score is not None]
    return PeriodCounts(start=span[0], end=span[1], calls=calls, meetings=len(found) - calls, total=len(found),
                        score=round(sum(values) / len(values), 2) if values else None, scored=len(values))  # fmt: skip


async def summary(
    principal: Principal, period: Literal["week", "month"], *, people: TenantRepo[Person],
    recordings: TenantRepo[Recording], analyses: TenantRepo[Analysis], now: datetime | None = None,
) -> Summary:  # fmt: skip
    current, previous = period_bounds(period, ist_day(now or utc_now()))
    person = await own_person(principal, people)
    if person is None:

        def empty(span: tuple[date, date]) -> PeriodCounts:
            return PeriodCounts(start=span[0], end=span[1], calls=0, meetings=0, total=0, score=None, scored=0)

        return Summary(period=period, current=empty(current), previous=empty(previous))
    return Summary(
        period=period,
        current=await _counts(person, current, recordings=recordings, analyses=analyses),
        previous=await _counts(person, previous, recordings=recordings, analyses=analyses),
    )


# --- Coaching (themes and learning history) ---


class ThemeOut(BaseModel):
    key: str
    name: str
    score: float | None  # last THEME_DAYS days
    previous: float | None  # the THEME_DAYS before
    count: int  # scores behind `score`


class PracticePoint(BaseModel):
    recording_id: str
    title: str
    interaction: Literal["call", "meeting"] | None
    client: str | None
    recorded_at: datetime
    text: str


class CoachingOut(BaseModel):
    themes: list[ThemeOut]
    focus: str | None  # the key of the weakest theme with a score
    practice_points: list[PracticePoint]


def _mean(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


async def coaching(
    principal: Principal, *, people: TenantRepo[Person], recordings: TenantRepo[Recording],
    analyses: TenantRepo[Analysis], scores: TenantRepo[Score], rubric: Rubric | None, now: datetime | None = None,
) -> CoachingOut:  # fmt: skip
    person = await own_person(principal, people)
    if person is None:
        return CoachingOut(themes=[], focus=None, practice_points=[])
    now = now or utc_now()
    theme_of = {d.key: d.theme for d in rubric.dimensions if d.theme} if rubric is not None else {}
    names = dict(rubric.themes or {}) if rubric is not None else {}
    split = now - timedelta(days=THEME_DAYS)
    rows = await scores.find({
        "person_id": person.id, "superseded": {"$ne": True}, "dimension": {"$in": sorted(theme_of)},
        "created_at": {"$gte": now - timedelta(days=2 * THEME_DAYS)},
    }, limit=10_000)  # fmt: skip
    recent: dict[str, list[int]] = {k: [] for k in names}
    before: dict[str, list[int]] = {k: [] for k in names}
    for row in rows:
        shown, theme = row.shown_score, theme_of.get(row.dimension)
        if shown is None or theme not in names:
            continue
        (recent if row.created_at >= split else before)[theme].append(shown)
    themes = [ThemeOut(key=k, name=n, score=_mean(recent[k]), previous=_mean(before[k]), count=len(recent[k]))
              for k, n in names.items()]  # fmt: skip
    scored = [t for t in themes if t.score is not None]
    focus = min(scored, key=lambda t: t.score or 0).key if scored else None

    found = await analyses.find(
        {"person_id": person.id, "conversation_type": "sales", "status": "COMPLETED", "superseded": {"$ne": True},
         "practice_point": {"$ne": None}},
        sort=[("created_at", -1)], limit=MAX_PRACTICE_POINTS,
    )  # fmt: skip
    by_id = {r.id: r for r in await recordings.find({"_id": {"$in": [a.recording_id for a in found]}})}
    points = [
        PracticePoint(
            recording_id=r.id,
            title=recording_title(r.file_name, r.id),
            interaction=interaction_of(r),
            client=r.client_name or a.client_said,
            recorded_at=r.recorded_at or r.created_at,
            text=a.practice_point,
        )
        for a in found
        if (r := by_id.get(a.recording_id)) is not None and a.practice_point is not None
    ]
    return CoachingOut(themes=themes, focus=focus, practice_points=points)
