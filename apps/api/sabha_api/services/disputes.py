"""Disputes (plan task P6.7, owner's decisions 2026-10-26): asking a reviewer to look again at one score.

- POST /v1/analyses/{id}/disputes {dimension_key, proposed_score, comment}: the person analysed (staff, own score),
  the managers of the recording's unit, owners and admins. Reviewers see the score but do not raise disputes (403).
  A meeting analyses nobody, so staff cannot dispute its scores; managers, owners and admins can. Only a shown score
  can be disputed (verified, applicable), with a score other than the one shown. At most one open dispute per score
  (a unique partial index; a second one is 409 dispute_open). Audited (dispute.create).
- GET /v1/disputes?status=: the reviewer's queue, newest first with cursor paging, filtered like the recordings
  list: owners and admins all, managers and reviewers their units. Staff never resolve (403).
- POST /v1/disputes/{id}/resolve {decision, final_score?, note}: reviewers and managers for their units, owners and
  admins for all; nobody decides a dispute they raised (403 own_dispute). Accepted needs a final score other than
  the one shown. One transaction: the dispute, the score (`human_score`; the AI's `score` stays as history), the
  analysis's overall score (recomputed with the reviewer's score; the AI's kept in `ai_overall_score`), an outbox
  event (`dispute.resolved`, for the notification) and the audit entry (dispute.resolve). Each decision is kept on
  the dispute as a calibration record: a person's score next to the AI's (P5.9).

The overall score is recomputed as the analysis computed it (sabha_analytics.synthesis.compute_overall): the
weighted mean of the verified, applicable scores, rounded half up to one decimal. Which dimensions count does not
change, so the verified share and the 60% rule do not either; an analysis without an overall score keeps none.
"""

from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from typing import Annotated, Any, Literal

from fastapi import Request
from pydantic import BaseModel, Field, StringConstraints
from pymongo.errors import DuplicateKeyError

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from sabha_api.services.results import VIEW_ALL, after_cursor, encode_cursor, recording_title, visible_recording
from sabha_api.services.reviews import RESOLVERS
from sabha_core.models import (
    Analysis,
    AuditEntry,
    Dispute,
    OutboxEvent,
    Person,
    Recording,
    Score,
    Unit,
    utc_now,
)  # fmt: skip
from sabha_core.profiles import ConversationType
from sabha_core.repo import TenantRepo

ROUTE = "POST /v1/analyses/{analysis_id}/disputes"
RAISERS = frozenset({Role.OWNER, Role.ADMIN, Role.MANAGER, Role.STAFF})
COMMENT_MIN, COMMENT_MAX = 10, 500  # the dialog's limits (apps/web/src/features/disputes/types.ts)
NOTE_MAX = 500
RESOLVED_EVENT = "dispute.resolved"


class NotDisputableError(BadRequestError):
    code, title = "not_disputable", "This score cannot be disputed"


class SameScoreError(BadRequestError):
    code, title = "same_score", "That is the score already shown"


class FinalScoreRequiredError(BadRequestError):
    code, title = "final_score_required", "Say which score is right"


class DisputeOpenError(ConflictError):
    code, title = "dispute_open", "A dispute about this score is already open"


class DisputeClosedError(ConflictError):
    code, title = "dispute_closed", "This dispute has already been decided"


class OwnDisputeError(ForbiddenError):
    code, title = "own_dispute", "You raised this dispute"


Comment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=COMMENT_MIN, max_length=COMMENT_MAX)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX)]


class DisputeIn(BaseModel):
    dimension_key: str = Field(min_length=1)
    proposed_score: int = Field(ge=1, le=5)
    comment: Comment


class ResolutionIn(BaseModel):
    decision: Literal["accepted", "rejected"]
    final_score: int | None = Field(default=None, ge=1, le=5, description="Required when accepted")
    note: Note


class DisputeOut(BaseModel):
    id: str
    analysis_id: str
    recording_id: str
    dimension_key: str
    dimension_name: str
    ai_score: int
    current_score: int  # the score shown when the dispute was raised
    proposed_score: int
    comment: str
    status: Literal["open", "accepted", "rejected", "closed"]
    final_score: int | None
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class Quote(BaseModel):
    quote: str
    start_ms: int


class DisputeItem(BaseModel):
    """One dispute in the reviewer's queue (ReviewItem kind "dispute" in apps/web/src/features/disputes/types.ts)."""

    kind: Literal["dispute"] = "dispute"
    id: str
    recording_id: str
    recording_title: str
    person_name: str | None
    unit: str | None
    dimension_key: str
    dimension_name: str
    ai_score: int
    current_score: int
    proposed_score: int
    comment: str
    evidence: list[Quote]
    status: Literal["open", "accepted", "rejected", "closed"]
    raised_by_me: bool  # then someone else decides it
    created_at: datetime


class DisputePage(BaseModel):
    items: list[DisputeItem]
    next_cursor: str | None


def dispute_out(d: Dispute) -> DisputeOut:
    return DisputeOut(
        id=d.id, analysis_id=d.analysis_id, recording_id=d.recording_id, dimension_key=d.dimension,
        dimension_name=d.dimension_name, ai_score=d.ai_score, current_score=d.current_score,
        proposed_score=d.proposed_score, comment=d.comment, status=d.status, final_score=d.final_score,
        resolution_note=d.resolution_note, created_at=d.created_at, resolved_at=d.resolved_at,
    )  # fmt: skip


def may_raise(principal: Principal, recording: Recording, analysis: Analysis) -> bool:
    """For a recording the caller can see: may they dispute its scores?"""
    if principal.role not in RAISERS:
        return False
    if principal.role is Role.STAFF:  # they see only their own recordings; a meeting analyses nobody
        return analysis.conversation_type is not ConversationType.MEETING and recording.person_id is not None
    return True


def overall_with(scores: list[Score]) -> float:
    """The weighted mean of the shown, verified and applicable scores, half up to one decimal (module docstring)."""
    counted = [s for s in scores if s.verified and not s.not_applicable and s.shown_score is not None]
    weight = sum((Fraction(str(s.weight)) for s in counted), Fraction(0))
    mean = sum((Fraction(str(s.weight)) * (s.shown_score or 0) for s in counted), Fraction(0)) / weight
    return float(Fraction(int(mean * 10 + Fraction(1, 2)), 10))


async def _visible_analysis(
    principal: Principal, analysis_id: str, analyses: TenantRepo[Analysis], recordings: TenantRepo[Recording],
    people: TenantRepo[Person],
) -> tuple[Analysis, Recording]:  # fmt: skip
    analysis = await analyses.find_one({"_id": analysis_id})
    if analysis is None:
        raise NotFoundError("This analysis does not exist or you cannot see it.")
    recording = await visible_recording(principal, analysis.recording_id, recordings, people)
    return analysis, recording


async def raise_dispute(
    principal: Principal, analysis_id: str, body: DisputeIn, request: Request, *, analyses: TenantRepo[Analysis],
    recordings: TenantRepo[Recording], people: TenantRepo[Person], scores: TenantRepo[Score],
    disputes: TenantRepo[Dispute], entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> DisputeOut:  # fmt: skip
    analysis, recording = await _visible_analysis(principal, analysis_id, analyses, recordings, people)
    if not may_raise(principal, recording, analysis):
        if principal.role is Role.REVIEWER:
            raise ForbiddenError("Reviewers decide disputes; the person analysed or their manager raises them.")
        raise ForbiddenError("Nobody is analysed in a meeting, so its scores are disputed by managers.")
    score = await scores.find_one({"analysis_id": analysis.id, "dimension": body.dimension_key})
    if analysis.superseded or score is None or not score.verified or score.not_applicable or score.score is None:
        raise NotDisputableError("Only a score shown in the report can be disputed.")
    current = score.shown_score or score.score
    if body.proposed_score == current:
        raise SameScoreError(f"The score shown is already {current}.")
    dispute = Dispute(
        tenant_id=principal.tenant_id, analysis_id=analysis.id, recording_id=recording.id,
        person_id=recording.person_id, unit_id=recording.unit_id, dimension=score.dimension,
        dimension_name=score.name, ai_score=score.score, current_score=current, proposed_score=body.proposed_score,
        comment=body.comment, raised_by=principal.user_id,
    )  # fmt: skip
    try:
        async with transactions.run() as session:
            await disputes.insert_one(dispute, session=session)
            await audit(entries, principal, request, action="dispute.create", target_type="dispute",
                        target_id=dispute.id, meta={"analysis_id": analysis.id, "dimension": score.dimension,
                                                    "proposed_score": body.proposed_score},
                        session=session)  # fmt: skip
    except DuplicateKeyError as exc:
        raise DisputeOpenError("A dispute about this score is already waiting for a reviewer.") from exc
    return dispute_out(dispute)


def _visible_disputes(principal: Principal) -> dict[str, Any]:
    if principal.role in VIEW_ALL:
        return {}
    return {"unit_id": {"$in": list(principal.unit_ids)}}


def require_resolver(principal: Principal) -> None:
    if principal.role not in RESOLVERS:
        raise ForbiddenError("Only reviewers, managers and administrators decide disputes.")


async def dispute_queue(
    principal: Principal, *, status: Literal["open", "accepted", "rejected"], cursor: str | None, limit: int,
    disputes: TenantRepo[Dispute], recordings: TenantRepo[Recording], people: TenantRepo[Person],
    units: TenantRepo[Unit], scores: TenantRepo[Score],
) -> DisputePage:  # fmt: skip
    require_resolver(principal)
    conditions = [c for c in (_visible_disputes(principal), after_cursor(cursor), {"status": status}) if c]
    found = await disputes.find({"$and": conditions}, sort=[("created_at", -1), ("_id", -1)], limit=limit + 1)
    page, more = found[:limit], len(found) > limit
    names = {p.id: p.name for p in await people.find({"_id": {"$in": [d.person_id for d in page if d.person_id]}})}
    unit_names = {u.id: u.name for u in await units.find({"_id": {"$in": [d.unit_id for d in page if d.unit_id]}})}
    files = {r.id: r.file_name for r in await recordings.find({"_id": {"$in": [d.recording_id for d in page]}})}
    quotes: dict[tuple[str, str], list[Quote]] = {}
    for s in await scores.find({"analysis_id": {"$in": [d.analysis_id for d in page]}}):
        quotes[(s.analysis_id, s.dimension)] = [Quote(quote=e["quote"], start_ms=e["start_ms"]) for e in s.evidence]
    items = []
    for d in page:
        title = recording_title(files.get(d.recording_id), d.recording_id)
        items.append(DisputeItem(
            id=d.id, recording_id=d.recording_id, recording_title=title, person_name=names.get(d.person_id or ""),
            unit=unit_names.get(d.unit_id or ""), dimension_key=d.dimension, dimension_name=d.dimension_name,
            ai_score=d.ai_score, current_score=d.current_score, proposed_score=d.proposed_score, comment=d.comment,
            evidence=quotes.get((d.analysis_id, d.dimension), []), status=d.status,
            raised_by_me=d.raised_by == principal.user_id, created_at=d.created_at,
        ))  # fmt: skip
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if more and page else None
    return DisputePage(items=items, next_cursor=next_cursor)


async def resolve(
    principal: Principal, dispute_id: str, body: ResolutionIn, request: Request, *, disputes: TenantRepo[Dispute],
    analyses: TenantRepo[Analysis], scores: TenantRepo[Score], outbox: TenantRepo[OutboxEvent],
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> DisputeOut:  # fmt: skip
    require_resolver(principal)
    dispute = await disputes.find_one({"_id": dispute_id, **_visible_disputes(principal)})
    if dispute is None:
        raise NotFoundError("This dispute does not exist or you cannot see it.")
    if dispute.raised_by == principal.user_id:
        raise OwnDisputeError("Someone other than the person who raised a dispute decides it.")
    if dispute.status != "open":
        raise DisputeClosedError("This dispute has already been decided.")
    accepted = body.decision == "accepted"
    if accepted and body.final_score is None:
        raise FinalScoreRequiredError("Give the final score when accepting a dispute.")
    if accepted and body.final_score == dispute.current_score:
        raise SameScoreError("Accepting with the score already shown changes nothing: reject the dispute instead.")
    analysis = await analyses.find_one({"_id": dispute.analysis_id})
    if analysis is None:
        raise NotFoundError("The analysis of this dispute no longer exists.")

    final = body.final_score if accepted else None
    now = utc_now()
    calibration = {"source": "dispute", "rubric_id": analysis.rubric_id, "rubric_version": analysis.rubric_version,
                   "dimension": dispute.dimension, "ai_score": dispute.ai_score,
                   "human_score": final if final is not None else dispute.current_score}  # fmt: skip
    decided = {"status": body.decision, "final_score": final, "resolution_note": body.note,
               "resolved_by": principal.user_id, "resolved_by_role": principal.role.value, "resolved_at": now,
               "calibration": calibration}  # fmt: skip
    meta = {"dispute_id": dispute.id, "analysis_id": dispute.analysis_id, "dimension": dispute.dimension,
            "decision": body.decision, "final_score": final, "note": body.note}  # fmt: skip
    async with transactions.run() as session:
        changed = await disputes.update_one({"_id": dispute.id, "status": "open"}, {"$set": decided}, session=session)
        if not changed:
            raise DisputeClosedError("Someone else decided this dispute first.")
        if final is not None:
            await scores.update_one({"analysis_id": dispute.analysis_id, "dimension": dispute.dimension},
                                    {"$set": {"human_score": final, "dispute_id": dispute.id}},
                                    session=session)  # fmt: skip
            if analysis.overall_score is not None:
                overall = overall_with(await scores.find({"analysis_id": analysis.id}, session=session))
                ai_overall = analysis.ai_overall_score or analysis.overall_score  # set once, by the first change
                changes = {"overall_score": overall, "ai_overall_score": ai_overall}
                await analyses.update_one({"_id": analysis.id}, {"$set": changes}, session=session)
        await outbox.insert_one(OutboxEvent(tenant_id=principal.tenant_id, type=RESOLVED_EVENT,
                                            payload={"dispute_id": dispute.id, "recording_id": dispute.recording_id,
                                                     "decision": body.decision}), session=session)  # fmt: skip
        await audit(entries, principal, request, action="dispute.resolve", target_type="dispute",
                    target_id=dispute.id, meta=meta, session=session)  # fmt: skip
    return dispute_out(dispute.model_copy(update={**decided, "resolved_by_role": principal.role}))


async def annotate_report(
    payload: dict[str, Any], principal: Principal, recording: Recording, analysis: Analysis | None, *,
    scores: TenantRepo[Score], disputes: TenantRepo[Dispute],
) -> dict[str, Any]:  # fmt: skip
    """Add what disputes change to a report payload: the overall score with reviewers' scores, each reviewed score's
    override (the AI score stays in `score`), which scores have an open dispute, and whether this viewer may
    dispute."""
    if analysis is None or "dimensions" not in payload:
        return payload
    reviewed = {s.dimension: s for s in await scores.find({"analysis_id": analysis.id, "human_score": {"$ne": None}})}
    decided = {d.id: d for d in await disputes.find({"_id": {"$in": [s.dispute_id for s in reviewed.values()]}})}
    open_keys = {d.dimension for d in await disputes.find({"analysis_id": analysis.id, "status": "open"})}
    dimensions = []
    for dimension in payload["dimensions"]:
        out = dict(dimension)
        if out.get("verified") and not out.get("not_applicable"):
            score = reviewed.get(out["key"])
            source = decided.get(score.dispute_id or "") if score is not None else None
            if score is not None and score.human_score is not None and source is not None:
                out["override"] = {
                    "score": score.human_score,
                    "reviewer_role": (source.resolved_by_role or Role.REVIEWER).value,
                    "note": source.resolution_note or "",
                    "resolved_at": (source.resolved_at or source.created_at).isoformat(),
                }
            out["dispute_open"] = out["key"] in open_keys
        dimensions.append(out)
    latest = payload.get("is_latest", True) and not analysis.superseded  # earlier versions are history only
    return {**payload, "dimensions": dimensions, "overall": analysis.overall_score,
            "can_dispute": latest and may_raise(principal, recording, analysis)}  # fmt: skip
