"""GET /v1/overview: the Overview page's numbers for a period (docs/design/01-overview.png), for the recordings
the caller may see (results.visible_filter: everything for owners and admins, their units for managers and
reviewers, their own for staff).

Every number is counted or taken from stored results (golden rule 6), with the count it rests on, so the page
can hide a number whose n is 0 instead of showing 0:

- the period's analysed recordings: those whose newest COMPLETED analysis was made in [from, to). A re-analysed
  recording counts once, with its newest result; NEEDS_REVIEW results are never counted (golden rule 5);
- the audio hours of those recordings (their original length);
- the median overall score per conversation type;
- "where coaching helps most": the median of each rubric dimension's verified scores, lowest first;
- what is in the pipeline right now (not limited to the period), by stage.

Not here yet: silence removed (it is in each recording's segment map, not in the database) and open disputes
(disputes are not built yet).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Literal

from pydantic import BaseModel, Field

from sabha_api.auth import Principal
from sabha_api.errors import BadRequestError
from sabha_api.services.results import visible_filter
from sabha_core.models import Analysis, Person, Recording, Score
from sabha_core.repo import TenantRepo

MAX_DAYS = 366
Stage = Literal["uploading", "queued", "preparing", "finding_speakers", "transcribing", "analysing", "needs_review"]
STAGES: dict[str, Stage] = {
    "CREATED": "uploading", "UPLOADED": "queued", "PREPROCESSING": "preparing", "DIARIZING": "finding_speakers",
    "TRANSCRIBING": "transcribing", "ANALYZING": "analysing", "NEEDS_REVIEW": "needs_review",
}  # fmt: skip


class TypeMedian(BaseModel):
    type: str
    median: float
    n: int


class CoachingItem(BaseModel):
    rubric_id: str
    dimension_key: str
    dimension_name: str
    type: str
    median: float
    n: int


class StageCount(BaseModel):
    stage: Stage
    n: int


class OverviewOut(BaseModel):
    from_: datetime = Field(serialization_alias="from")  # `from` is a Python keyword
    to: datetime
    recordings_analysed: int
    audio_hours: float
    median_overall_by_type: list[TypeMedian]
    coaching: list[CoachingItem]  # lowest median first
    in_progress: list[StageCount]  # right now, whatever the period; stages with none are left out


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def check_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise BadRequestError("`to` must be after `from`.")
    if end - start > timedelta(days=MAX_DAYS):
        raise BadRequestError(f"The period can be at most {MAX_DAYS} days.")
    return start, end


async def overview(
    principal: Principal, start: datetime, end: datetime, *, people: TenantRepo[Person],
    recordings: TenantRepo[Recording], analyses: TenantRepo[Analysis], scores: TenantRepo[Score],
) -> OverviewOut:  # fmt: skip
    start, end = check_period(start, end)
    visible = await visible_filter(principal, people)
    # Analyses are matched through the recordings the caller may see, exactly as the recordings list does (not
    # through the unit copied onto each analysis, which could disagree if a recording moved). Owners and admins
    # see everything, so they need no list.
    scope: dict[str, object] = {}
    if visible:
        scope = {"recording_id": {"$in": [r.id for r in await recordings.find(visible)]}}

    found = await analyses.find(
        {**scope, "status": "COMPLETED", "created_at": {"$gte": start, "$lt": end}}, sort=[("created_at", 1)]
    )
    newest: dict[str, Analysis] = {}
    for analysis in found:
        newest[analysis.recording_id] = analysis  # ascending, so the newest wins
    # A recording re-analysed after the period ends belongs to the later period: its newest result is not here.
    later = await analyses.find({"status": "COMPLETED", "recording_id": {"$in": list(newest)},
                                 "created_at": {"$gte": end}}) if newest else []  # fmt: skip
    for analysis in later:
        newest.pop(analysis.recording_id, None)

    lengths = await recordings.find({"_id": {"$in": list(newest)}}) if newest else []
    audio_ms = sum(r.duration_ms or 0 for r in lengths)

    by_type: dict[str, list[float]] = {}
    for analysis in newest.values():
        if analysis.overall_score is not None:
            by_type.setdefault(analysis.conversation_type.value, []).append(analysis.overall_score)

    by_id = {a.id: a for a in newest.values()}
    dimension_scores = await scores.find({"analysis_id": {"$in": list(by_id)}, "verified": True}) if by_id else []
    groups: dict[tuple[str, str], tuple[str, str, list[int]]] = {}
    for score in dimension_scores:
        shown = score.shown_score  # a reviewer's score from an accepted dispute counts (P6.7)
        if shown is None:  # not applicable to this recording: no score to count
            continue
        analysis = by_id[score.analysis_id]
        key = (analysis.rubric_id, score.dimension)
        groups.setdefault(key, (score.name, analysis.conversation_type.value, []))[2].append(shown)
    coaching = sorted(
        (CoachingItem(rubric_id=rubric_id, dimension_key=dimension, dimension_name=name, type=kind,
                      median=round(median(values), 2), n=len(values))
         for (rubric_id, dimension), (name, kind, values) in groups.items()),
        key=lambda item: (item.median, -item.n, item.dimension_name),
    )  # fmt: skip

    in_progress = []
    for status, stage in STAGES.items():
        n = await recordings.count({**visible, "status": status})
        if n:
            in_progress.append(StageCount(stage=stage, n=n))

    medians = [TypeMedian(type=t, median=round(median(v), 2), n=len(v)) for t, v in sorted(by_type.items())]
    return OverviewOut(
        from_=start, to=end, recordings_analysed=len(newest), audio_hours=round(audio_ms / 3_600_000, 2),
        median_overall_by_type=medians, coaching=coaching, in_progress=in_progress,
    )  # fmt: skip
