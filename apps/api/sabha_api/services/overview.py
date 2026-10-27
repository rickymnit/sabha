"""GET /v1/overview: the Overview page's numbers for a period (UI v2, docs/design/v2/01-overview.png), for the
recordings the caller may see (results.visible_filter: everything for owners and admins, their units for managers
and reviewers, their own for staff), optionally narrowed to one unit and the units under it (`unit_id`, the campus
switcher). The narrowing is AND-ed with what the caller may see, so it never shows more.

Every number is counted or taken from stored results (golden rule 6), with the count it rests on, so the page can
hide a number whose n is 0 instead of showing 0:

- a recording belongs to the period of its newest COMPLETED analysis: re-analysed, it counts once, with its newest
  result, in the period that result was made; NEEDS_REVIEW results are never counted (golden rule 5);
- per period: recordings analysed, their audio hours (original length), the silence skipped (only recordings whose
  speech time is stored; `silence_n` says how many), the median overall score per conversation type, and reception
  tickets and how many were resolved (tickets with verified quotes only);
- `series`: SERIES_PERIODS periods of the same length ending with this one (oldest first; the last is this period,
  the one before it the previous period) for the tiles' "up/down" and sparklines;
- "where coaching helps most": the median of each rubric dimension's verified scores, lowest first, with the same
  median per top-level unit (`by_unit`) and per week for the TREND_WEEKS weeks ending at `to` (`weekly`);
- right now, whatever the period: what is in the pipeline by stage, the newest few recordings in it, and the median
  time from upload to finished report per type over the last TURNAROUND_DAYS.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Literal

from pydantic import BaseModel, Field

from sabha_api.auth import Principal
from sabha_api.errors import BadRequestError
from sabha_api.services.results import recording_title, visible_filter
from sabha_core.models import Analysis, Person, Recording, Score, Unit, utc_now
from sabha_core.repo import TenantRepo
from sabha_core.state import RecordingStatus

MAX_DAYS = 366
SERIES_PERIODS = 8
TREND_WEEKS = 8
PROCESSING_ITEMS = 3
TURNAROUND_DAYS = 30
Stage = Literal["uploading", "queued", "preparing", "finding_speakers", "transcribing", "analysing", "needs_review"]
STAGES: dict[str, Stage] = {
    "CREATED": "uploading", "UPLOADED": "queued", "PREPROCESSING": "preparing", "DIARIZING": "finding_speakers",
    "TRANSCRIBING": "transcribing", "ANALYZING": "analysing", "NEEDS_REVIEW": "needs_review",
}  # fmt: skip
WEEK = timedelta(days=7)


class TypeMedian(BaseModel):
    type: str
    median: float
    n: int


class UnitMedian(BaseModel):
    unit_id: str
    median: float
    n: int


class WeekMedian(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    median: float | None  # None: no verified score that week
    n: int


class CoachingItem(BaseModel):
    rubric_id: str
    dimension_key: str
    dimension_name: str
    type: str
    median: float
    n: int
    by_unit: list[UnitMedian] = []  # top-level units with scores, by name
    weekly: list[WeekMedian] = []  # TREND_WEEKS weeks ending at `to`, oldest first


class StageCount(BaseModel):
    stage: Stage
    n: int


class ProcessingItem(BaseModel):
    id: str
    title: str
    type: str
    stage: Stage
    person_name: str | None


class Turnaround(BaseModel):
    type: str
    minutes: float  # median, upload complete to report
    n: int


class Period(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    recordings_analysed: int
    audio_hours: float
    silence_hours: float
    silence_n: int  # recordings whose speech time is known; silence_hours covers only these
    median_overall_by_type: list[TypeMedian]
    tickets: int  # reception calls with a ticket
    tickets_resolved: int


class UnitRef(BaseModel):
    id: str
    name: str


class OverviewOut(Period):
    unit_id: str | None
    units: list[UnitRef]  # top-level units the caller may see: the campus switcher
    series: list[Period]  # SERIES_PERIODS periods of this length, oldest first; the last is this period
    coaching: list[CoachingItem]  # lowest median first
    in_progress: list[StageCount]  # right now, whatever the period; stages with none are left out
    processing: list[ProcessingItem]  # the newest few in the pipeline (not NEEDS_REVIEW)
    turnaround: list[Turnaround]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def check_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise BadRequestError("`to` must be after `from`.")
    if end - start > timedelta(days=MAX_DAYS):
        raise BadRequestError(f"The period can be at most {MAX_DAYS} days.")
    return start, end


def subtree(units: Iterable[Unit], unit_id: str) -> set[str]:
    """The unit and every unit under it, at any depth (a circular parent chain is walked once)."""
    children: dict[str, list[str]] = {}
    for u in units:
        if u.parent_id:
            children.setdefault(u.parent_id, []).append(u.id)
    found, todo = {unit_id}, [unit_id]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def roots_of(units: Iterable[Unit]) -> dict[str, str]:
    """Each unit's top-level unit (itself when it has no parent). A broken chain (a missing or circular parent)
    stops at the last unit found."""
    parents = {u.id: u.parent_id for u in units}
    roots: dict[str, str] = {}
    for unit_id in parents:
        seen, current = {unit_id}, unit_id
        while (parent := parents.get(current)) and parent in parents and parent not in seen:
            seen.add(parent)
            current = parent
        roots[unit_id] = current
    return roots


def _median(values: Sequence[float]) -> float:
    return round(median(values), 2)


def _period(start: datetime, end: datetime, newest: list[Analysis], by_id: dict[str, Recording]) -> Period:
    inside = [a for a in newest if start <= a.created_at < end]
    lengths = [by_id[a.recording_id] for a in inside if a.recording_id in by_id]
    known = [r for r in lengths if r.duration_ms is not None and r.speech_ms is not None]
    by_type: dict[str, list[float]] = {}
    for a in inside:
        if a.overall_score is not None:
            by_type.setdefault(a.conversation_type.value, []).append(a.overall_score)
    tickets = [a for a in inside if a.ticket_status is not None]
    return Period(
        from_=start, to=end, recordings_analysed=len(inside),
        audio_hours=round(sum(r.duration_ms or 0 for r in lengths) / 3_600_000, 2),
        silence_hours=round(sum((r.duration_ms or 0) - (r.speech_ms or 0) for r in known) / 3_600_000, 2),
        silence_n=len(known),
        median_overall_by_type=[TypeMedian(type=t, median=_median(v), n=len(v)) for t, v in sorted(by_type.items())],
        tickets=len(tickets), tickets_resolved=sum(1 for a in tickets if a.ticket_status == "resolved"),
    )  # fmt: skip


async def overview(
    principal: Principal, start: datetime, end: datetime, *, unit_id: str | None = None,
    people: TenantRepo[Person], recordings: TenantRepo[Recording], analyses: TenantRepo[Analysis],
    scores: TenantRepo[Score], units: TenantRepo[Unit],
) -> OverviewOut:  # fmt: skip
    start, end = check_period(start, end)
    length = end - start
    all_units = await units.find({}, sort=[("name", 1)])
    roots = roots_of(all_units)
    names = {u.id: u.name for u in all_units}

    visible = await visible_filter(principal, people)
    conditions = [visible] if visible else []
    if unit_id is not None:
        conditions.append({"unit_id": {"$in": sorted(subtree(all_units, unit_id))}})
    scope: dict[str, object] = {"$and": conditions} if conditions else {}
    # The switcher: every top-level unit for those who see everything, the top of their own units for managers and
    # reviewers, none for staff (who see only their own recordings).
    mine = roots.values() if not visible else (roots.get(u, u) for u in principal.unit_ids)
    switcher = sorted(set(mine) & set(names), key=lambda u: names[u])

    # One read covers every bucket: from the oldest series period or trend week, with no upper bound, so a result
    # made after `to` moves its recording out of every earlier period.
    # Analyses are matched through the recordings the caller may see, exactly as the recordings list does (not
    # through the unit copied onto each analysis, which could disagree if a recording moved). Someone who sees
    # everything, with no unit chosen, needs no list: only the recordings the analyses point at are read.
    window = min(end - length * SERIES_PERIODS, end - WEEK * TREND_WEEKS)
    query: dict[str, object] = {"status": "COMPLETED", "created_at": {"$gte": window}}
    if conditions:
        query["recording_id"] = {"$in": [r.id for r in await recordings.find(scope)]}
    found = await analyses.find(query, sort=[("created_at", 1)])
    latest: dict[str, Analysis] = {}
    for analysis in found:
        latest[analysis.recording_id] = analysis  # ascending, so the newest wins
    by_id = {r.id: r for r in await recordings.find({"_id": {"$in": list(latest)}})} if latest else {}
    latest = {rid: a for rid, a in latest.items() if rid in by_id}
    newest = [a for a in latest.values() if a.created_at < end]

    series = [
        _period(end - length * (SERIES_PERIODS - i), end - length * (SERIES_PERIODS - 1 - i), newest, by_id)
        for i in range(SERIES_PERIODS)
    ]  # the last one is [start, end)

    # Coaching: verified dimension scores of the newest analyses in this period (by unit) and in each trend week.
    weeks = [(end - WEEK * (TREND_WEEKS - i), end - WEEK * (TREND_WEEKS - 1 - i)) for i in range(TREND_WEEKS)]
    wanted = [a for a in newest if a.created_at >= min(start, weeks[0][0])]
    by_analysis = {a.id: a for a in wanted}
    dimension_scores = await scores.find({"analysis_id": {"$in": list(by_analysis)},
                                          "verified": True}) if by_analysis else []  # fmt: skip
    groups: dict[tuple[str, str], tuple[str, str]] = {}
    period_values: dict[tuple[str, str], list[int]] = {}
    unit_values: dict[tuple[str, str], dict[str, list[int]]] = {}
    week_values: dict[tuple[str, str], list[list[int]]] = {}
    for score in dimension_scores:
        shown = score.shown_score  # a reviewer's score from an accepted dispute counts (P6.7)
        if shown is None:  # not applicable to this recording: no score to count
            continue
        analysis = by_analysis[score.analysis_id]
        key = (analysis.rubric_id, score.dimension)
        groups.setdefault(key, (score.name, analysis.conversation_type.value))
        weekly = week_values.setdefault(key, [[] for _ in weeks])
        for i, (lo, hi) in enumerate(weeks):
            if lo <= analysis.created_at < hi:
                weekly[i].append(shown)
        if start <= analysis.created_at < end:
            period_values.setdefault(key, []).append(shown)
            unit = by_id[analysis.recording_id].unit_id
            if unit:
                unit_values.setdefault(key, {}).setdefault(roots.get(unit, unit), []).append(shown)
    coaching = sorted(
        (CoachingItem(
            rubric_id=rubric_id, dimension_key=dimension, dimension_name=groups[(rubric_id, dimension)][0],
            type=groups[(rubric_id, dimension)][1], median=_median(values), n=len(values),
            by_unit=[UnitMedian(unit_id=u, median=_median(v), n=len(v))
                     for u, v in sorted(unit_values.get((rubric_id, dimension), {}).items(),
                                        key=lambda kv: names.get(kv[0], kv[0]))],
            weekly=[WeekMedian(from_=lo, median=_median(v) if v else None, n=len(v))
                    for (lo, _), v in zip(weeks, week_values[(rubric_id, dimension)], strict=True)],
        ) for (rubric_id, dimension), values in period_values.items()),
        key=lambda item: (item.median, -item.n, item.dimension_name),
    )  # fmt: skip

    in_progress = []
    for status, stage in STAGES.items():
        n = await recordings.count({"$and": [*conditions, {"status": status}]})
        if n:
            in_progress.append(StageCount(stage=stage, n=n))
    running = [s for s in STAGES if s != RecordingStatus.NEEDS_REVIEW.value]
    busy = await recordings.find({"$and": [*conditions, {"status": {"$in": running}}]},
                                 sort=[("created_at", -1)], limit=PROCESSING_ITEMS)  # fmt: skip
    person_ids = sorted({r.person_id for r in busy if r.person_id})
    person_names = {p.id: p.name for p in await people.find({"_id": {"$in": person_ids}})} if person_ids else {}
    processing = [ProcessingItem(id=r.id, title=recording_title(r.file_name, r.id), type=r.type.value,
                                 stage=STAGES[r.status.value], person_name=person_names.get(r.person_id or ""))
                  for r in busy]  # fmt: skip

    since = utc_now() - timedelta(days=TURNAROUND_DAYS)
    # First runs only: a re-analysis moves status_changed_at days later and would inflate the time.
    first_runs = {
        "status": RecordingStatus.COMPLETED.value,
        "status_changed_at": {"$gte": since},
        "analysis_run": {"$in": [1, None]},
    }  # recordings from before re-analysis have no analysis_run
    done = await recordings.find({"$and": [*conditions, first_runs]})
    minutes: dict[str, list[float]] = {}
    for r in done:
        if r.completed_at and r.status_changed_at and r.status_changed_at >= r.completed_at:
            minutes.setdefault(r.type.value, []).append((r.status_changed_at - r.completed_at).total_seconds() / 60)
    turnaround = [Turnaround(type=t, minutes=round(median(v), 1), n=len(v)) for t, v in sorted(minutes.items())]

    current = series[-1]
    return OverviewOut(
        **current.model_dump(), unit_id=unit_id,
        units=[UnitRef(id=u, name=names[u]) for u in switcher],
        series=series, coaching=coaching, in_progress=in_progress, processing=processing, turnaround=turnaround,
    )  # fmt: skip
