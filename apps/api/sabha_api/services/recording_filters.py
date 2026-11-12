"""The Recordings page's tabs and filters (UI v2, docs/design/v2/02-recordings.png), as MongoDB conditions.

Each condition is AND-ed with the caller's visibility filter by the list, counts and export, so a filter can only
narrow what someone may see, never widen it.

- unit_id: that unit and every unit under it (a campus and its classes).
- score: the latest analysis's overall score in the band people see (design.score.scoreBand in the web app: the
  cut is on the one-decimal value shown, so 2.96 shows as 3.0 and is not "below 3").
- recorded_from / recorded_to: IST calendar days, both included, on the recording's date (when it was recorded,
  else when it was uploaded).
- tab "decision" (owner's decision 2026-11-03): what needs a person, the same things the Overview's "Needs your
  decision" card lists: needs review, an open score dispute, or failed and not yet closed (an open dead letter).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from sabha_core.models import Analysis, DeadLetter, Dispute, Unit
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo
from sabha_core.state import RecordingStatus
from sabha_core.units import subtree

ScoreBand = Literal["below_3", "mid", "good"]
IST = timedelta(hours=5, minutes=30)


class ListFilter(BaseModel):
    type: ConversationType | None = None
    person_id: str | None = None
    unit_id: str | None = None
    score: ScoreBand | None = None
    recorded_from: date | None = None
    recorded_to: date | None = None
    tab: Literal["decision"] | None = None
    interaction: Literal["call", "meeting"] | None = None  # sales calls or meetings (older sales ones are meetings)


def list_filter(
    type: ConversationType | None = None, person_id: str | None = None, unit_id: str | None = None,
    score: ScoreBand | None = None, recorded_from: date | None = None, recorded_to: date | None = None,
    tab: Literal["decision"] | None = None, interaction: Literal["call", "meeting"] | None = None,
) -> ListFilter:  # fmt: skip
    """The filters as query parameters (a FastAPI dependency)."""
    return ListFilter(type=type, person_id=person_id, unit_id=unit_id, score=score, recorded_from=recorded_from,
                      recorded_to=recorded_to, tab=tab, interaction=interaction)  # fmt: skip


def band(score: float) -> ScoreBand:
    shown = round(score, 1)
    return "below_3" if shown < 3 else "mid" if shown < 3.8 else "good"


def _ist_day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC) - IST


async def scored_ids(analyses: TenantRepo[Analysis], wanted: ScoreBand) -> list[str]:
    """Recordings whose latest analysis has an overall score in `wanted`."""
    rows = await analyses.aggregate([
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$recording_id", "score": {"$first": "$overall_score"}}},
    ])  # fmt: skip
    return sorted(r["_id"] for r in rows if r["score"] is not None and band(float(r["score"])) == wanted)


async def decision_condition(dlq: TenantRepo[DeadLetter], disputes: TenantRepo[Dispute]) -> dict[str, Any]:
    open_letters = await dlq.find({"replayed_at": None, "abandoned_at": None})
    disputed = await disputes.find({"status": "open"})
    failed = sorted({d.recording_id for d in open_letters})
    return {
        "$or": [
            {"status": RecordingStatus.NEEDS_REVIEW.value},
            {"status": RecordingStatus.FAILED.value, "_id": {"$in": failed}},
            {"_id": {"$in": sorted({d.recording_id for d in disputed})}},
        ]
    }


async def filter_conditions(
    f: ListFilter, *, units: TenantRepo[Unit], analyses: TenantRepo[Analysis], dlq: TenantRepo[DeadLetter],
    disputes: TenantRepo[Dispute],
) -> list[dict[str, Any]]:  # fmt: skip
    conditions: list[dict[str, Any]] = []
    if f.person_id is not None:
        conditions.append({"person_id": f.person_id})
    if f.type is not None:
        conditions.append({"type": f.type.value})
    if f.interaction == "call":
        conditions.append({"type": "sales", "interaction": "call"})
    elif f.interaction == "meeting":
        conditions.append({"type": "sales", "interaction": {"$ne": "call"}})
    if f.unit_id is not None:
        conditions.append({"unit_id": {"$in": sorted(subtree(await units.find({}), [f.unit_id]))}})
    if f.score is not None:
        conditions.append({"_id": {"$in": await scored_ids(analyses, f.score)}})
    if f.recorded_from is not None or f.recorded_to is not None:
        span: dict[str, datetime] = {}
        if f.recorded_from is not None:
            span["$gte"] = _ist_day_start(f.recorded_from)
        if f.recorded_to is not None:
            span["$lt"] = _ist_day_start(f.recorded_to + timedelta(days=1))
        conditions.append({"$or": [{"recorded_at": span}, {"recorded_at": None, "created_at": span}]})
    if f.tab == "decision":
        conditions.append(await decision_condition(dlq, disputes))
    return conditions
