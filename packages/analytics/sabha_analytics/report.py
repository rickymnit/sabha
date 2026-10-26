"""The analysis report: scoring, overall score and synthesis joined into one validated document (plan task P5.7).

`analyse()` runs the whole pure part of the analyze stage (no MongoDB, no queue): score every dimension with
verified evidence (scoring.py), compute the overall score from verified dimensions only, ask for the synthesis when
there is an overall score (synthesis.py), and assemble an `analysis@v1` report. The analyze task (P2.4/P5.7 wiring)
stores it and makes the status transition the report names.

What the report guarantees (`check_report` enforces it in code; schemas/analysis.v1.schema.json documents it):

- An unverified dimension has `verified: false`, no score, no rationale and no evidence; only its failure codes
  remain, for review. It is never shown to staff (golden rule 5).
- Every evidence item is a verified quote, and the quote stored is the transcript's own matched wording (redacted),
  never the model's text, with the matched utterance's id and ORIGINAL-timeline times. A fabricated quote cannot
  appear anywhere in the report.
- The report holds no PII: transcript text is redacted, and authorised users see original wording only through the
  redaction mapping, server-side (P5.7b).
- `next_status` is COMPLETED, or NEEDS_REVIEW with `review_reasons` ("low_verification" when less than 60% of the
  rubric weight is verified, "synthesis_failed" when the synthesis failed twice). Both are valid transitions from
  ANALYZING in sabha_core.state.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from sabha_analytics.classify import UNCERTAIN_TYPE, Classification
from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.meetings import MeetingNotesOutcome, write_meeting_notes
from sabha_analytics.phases import PhaseOutcome, segment_phases
from sabha_analytics.reception import TICKET_FAILED, TicketOutcome, ticket_values, write_ticket
from sabha_analytics.sales import DealCardOutcome, interest_values, write_deal_card
from sabha_analytics.scoring import (
    CallRecord,
    DimensionResult,
    JudgeModel,
    RubricSpec,
    TokenUsage,
    score_dimensions,
)
from sabha_analytics.synthesis import (
    LOW_VERIFICATION,
    SYNTHESIS_FAILED,
    OverallScore,
    SynthesisOutcome,
    compute_overall,
    synthesise,
)
from sabha_core.state import RecordingStatus, check_transition

ANALYSIS_VERSION = "analysis@v1"


class InvalidReport(ValueError):
    """The assembled report breaks a guarantee in the module docstring. Nothing should be stored."""


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    report: dict[str, Any]
    next_status: RecordingStatus


def _dimension_record(dimension: DimensionResult) -> dict[str, Any]:
    record: dict[str, Any] = {
        "key": dimension.key,
        "name": dimension.name,
        "weight": dimension.weight,
        "verified": dimension.verified,
        "attempts": dimension.attempts,
        # Counts only: unverified quotes themselves are never stored (golden rule 5).
        "grounding": {"quotes_offered": dimension.quotes_offered, "quotes_verified": dimension.quotes_verified},
    }
    if not dimension.verified:
        return {
            **record,
            "score": None,
            "rationale": None,
            "evidence": [],
            "failure_reasons": list(dimension.failure_reasons),
        }
    if dimension.not_applicable:
        record["not_applicable"] = True
    return {
        **record,
        "score": dimension.score,
        "rationale": dimension.rationale,
        "evidence": [
            {"quote": e.matched_text, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}
            for e in dimension.evidence
            if e.verified
        ],
        "failure_reasons": [],
    }


def _usage(calls: Iterable[CallRecord]) -> dict[str, Any]:
    calls = tuple(calls)
    total = sum((call.usage for call in calls), TokenUsage())
    return {
        "total": total.to_record(),
        "calls": [
            {
                "task": c.task,
                "attempt": c.attempt,
                "keys": list(c.keys),
                "model_id": c.model_id,
                "usage": c.usage.to_record(),
            }
            for c in calls
        ],
    }


def build_report(
    *,
    rubric: RubricSpec,
    transcript: PreparedTranscript,
    dimensions: tuple[DimensionResult, ...],
    metrics: tuple[dict[str, Any], ...],
    overall: OverallScore,
    synthesis: SynthesisOutcome | None,
    calls: tuple[CallRecord, ...],
    prompt_hashes: Mapping[str, Mapping[str, str]],
    classification: Classification | None = None,
    phases: PhaseOutcome | None = None,
    ticket: TicketOutcome | None = None,
    deal_card: DealCardOutcome | None = None,
    meeting_notes: MeetingNotesOutcome | None = None,
) -> AnalysisResult:
    """Assemble and check an analysis@v1 report (module docstring)."""
    reasons: list[str] = []
    if classification is not None and classification.needs_review_reason is not None:
        reasons.append(classification.needs_review_reason)
    elif overall.score is None:
        reasons.append(LOW_VERIFICATION)
    elif synthesis is None or synthesis.synthesis is None:
        reasons.append(SYNTHESIS_FAILED)
    if ticket is not None and ticket.ticket is None:
        reasons.append(TICKET_FAILED)
    status = RecordingStatus.NEEDS_REVIEW if reasons else RecordingStatus.COMPLETED
    check_transition(RecordingStatus.ANALYZING, status)

    summary = synthesis.synthesis if synthesis is not None else None
    report: dict[str, Any] = {
        "version": ANALYSIS_VERSION,
        "rubric": {"id": rubric.id, "version": rubric.version},
        "transcript": {"sha256": transcript.sha256, "asr_model": transcript.asr_model},
        "overall": {
            "score": overall.score,
            "verified_share": overall.verified_share,
            "verified_weight": overall.verified_weight,
            "total_weight": overall.total_weight,
        },
        "dimensions": [_dimension_record(d) for d in dimensions],
        "metrics": [dict(m) for m in metrics],
        "synthesis": None
        if summary is None
        else {
            "summary": summary.summary,
            "strengths": list(summary.strengths),
            "gaps": list(summary.gaps),
            "suggestions": [
                {"text": s.text, "utterance_id": s.utterance_id, "start_ms": s.start_ms, "end_ms": s.end_ms}
                for s in summary.suggestions
            ],
        },
        "next_status": status.value,
        "review_reasons": reasons,
        "model_ids": sorted({c.model_id for c in calls}),
        "prompts": {name: dict(record) for name, record in sorted(prompt_hashes.items())},
        "usage": _usage(calls),
        "classification": None
        if classification is None
        else {
            "type": classification.type,
            "language_mix": classification.language_mix,
            "confidence": classification.confidence,
        },
        "phases": None
        if phases is None or phases.phases is None
        else [
            {
                "phase": ph.name,
                "start_utterance_id": ph.start_utterance_id,
                "end_utterance_id": ph.end_utterance_id,
                "start_ms": ph.start_ms,
                "end_ms": ph.end_ms,
            }
            for ph in phases.phases
        ],
        # Reception: shown only with both quotes verified (sabha_analytics.reception).
        "ticket": None if ticket is None or ticket.ticket is None else ticket.ticket.to_record(),
        # Sales: verified items only (sabha_analytics.sales). No card is not a reason for review.
        "deal_card": None if deal_card is None or deal_card.card is None else deal_card.card.to_record(),
        # Meetings: verified items only (sabha_analytics.meetings). No notes is not a reason for review.
        "meeting_notes": None
        if meeting_notes is None or meeting_notes.notes is None
        else meeting_notes.notes.to_record(),
    }
    check_report(report, transcript)
    return AnalysisResult(report, status)


def check_report(report: Mapping[str, Any], transcript: PreparedTranscript) -> None:
    """Raise InvalidReport unless every guarantee in the module docstring holds."""
    problems: list[str] = []
    for dimension in report["dimensions"]:
        key = dimension["key"]
        if not dimension["verified"]:
            if dimension["score"] is not None or dimension["rationale"] is not None or dimension["evidence"]:
                problems.append(f"{key}: an unverified dimension carries a score, rationale or evidence")
            continue
        if dimension.get("not_applicable"):
            if dimension["score"] is not None or not dimension["rationale"] or not dimension["evidence"]:
                problems.append(f"{key}: a not-applicable dimension needs no score, a rationale and evidence")
        elif not isinstance(dimension["score"], int) or not 1 <= dimension["score"] <= 5:
            problems.append(f"{key}: verified dimension without a score from 1 to 5")
        for item in dimension["evidence"]:
            utterance = transcript.get(item["utterance_id"])
            if utterance is None:
                problems.append(f"{key}: evidence points at unknown utterance {item['utterance_id']!r}")
            elif item["quote"] not in utterance.text:
                problems.append(f"{key}: evidence quote is not the transcript's own wording")
            elif (item["start_ms"], item["end_ms"]) != (utterance.start_ms, utterance.end_ms):
                problems.append(f"{key}: evidence times differ from the transcript")
    synthesis = report["synthesis"]
    if synthesis is not None:
        for suggestion in synthesis["suggestions"]:
            if transcript.get(suggestion["utterance_id"]) is None:
                problems.append(f"suggestion points at unknown utterance {suggestion['utterance_id']!r}")
    for phase in report.get("phases") or []:
        for uid in (phase["start_utterance_id"], phase["end_utterance_id"]):
            if transcript.get(uid) is None:
                problems.append(f"phase {phase['phase']} points at unknown utterance {uid!r}")
    card = report.get("deal_card") or {}
    evidence = [
        *(item["evidence"] for item in card.get("current_setup", [])),
        *(item["evidence"] for item in card.get("customer_needs", [])),
        *(item["evidence"] for item in card.get("objections", [])),
        *([card["next_step"]["evidence"]] if card.get("next_step") else []),
        *([card["interest_level"]["evidence"]] if (card.get("interest_level") or {}).get("evidence") else []),
    ]
    ticket = report.get("ticket") or {}
    evidence += list((ticket.get("evidence") or {}).values())
    notes = report.get("meeting_notes") or {}
    evidence += [
        item["evidence"] for key in ("decisions", "action_items", "open_questions") for item in notes.get(key, [])
    ]
    for item in evidence:
        utterance = transcript.get(item["utterance_id"])
        if utterance is None or item["quote"] not in utterance.text:
            problems.append(f"ticket, deal card or notes quote is not the transcript's own wording: {item['quote']!r}")
        elif (item["start_ms"], item["end_ms"]) != (utterance.start_ms, utterance.end_ms):
            problems.append("ticket, deal card or notes evidence times differ from the transcript")
    if report["overall"]["score"] is None and report["next_status"] != RecordingStatus.NEEDS_REVIEW.value:
        problems.append("no overall score, but the report does not ask for review")
    if problems:
        raise InvalidReport("; ".join(problems))


def load_report_schema() -> dict[str, Any]:
    """The analysis@v1 JSON Schema (the contract for the analysis API and the web app)."""
    text = files("sabha_analytics").joinpath("schemas/analysis.v1.schema.json").read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def analyse(
    *,
    rubric: RubricSpec,
    transcript: PreparedTranscript,
    metrics: Iterable[Mapping[str, object]],
    model: JudgeModel,
    analysed_roles: Collection[str],
    classification: Classification | None = None,
    phase_names: Sequence[str] | None = None,
    reception: bool = False,
    sales: bool = False,
    meeting: bool = False,
) -> AnalysisResult:
    """Score, compute the overall score, synthesise when there is one, and assemble the report.

    `classification`: the result of classify.classify when the type had to be inferred. If it asks for review
    ("uncertain_type"), nothing is scored, because the rubric itself is in doubt. `phase_names`: split the
    conversation into these phases for the timeline. `sales`: also write the meeting's deal card, with the interest
    levels of the rubric's `output_values.interest_level` (ValueError before any model call if it has none).
    `meeting`: also write the meeting's notes (decisions, action items, open questions).
    `reception`: also write the call's ticket, with the categories
    and statuses of the rubric's `output_values` (ValueError before any model call if the rubric has none).
    """
    if classification is not None and classification.needs_review_reason == UNCERTAIN_TYPE:
        empty = compute_overall(())
        return build_report(
            rubric=rubric,
            transcript=transcript,
            dimensions=(),
            metrics=(),
            overall=empty,
            synthesis=None,
            calls=classification.calls,
            prompt_hashes={p.name: p.to_record() for p in classification.prompts},
            classification=classification,
        )
    values = ticket_values(rubric.output_values) if reception else None
    interest = interest_values(rubric.output_values) if sales else None
    scoring = score_dimensions(rubric=rubric, transcript=transcript, metrics=metrics, model=model)
    overall = compute_overall(scoring.dimensions)
    synthesis = None
    if overall.score is not None:
        synthesis = synthesise(
            rubric_id=rubric.id,
            rubric_version=rubric.version,
            dimensions=scoring.dimensions,
            metrics=scoring.metrics,
            transcript=transcript,
            model=model,
            analysed_roles=analysed_roles,
            rubric_roles=tuple(rubric.roles),
        )
    phases = segment_phases(transcript, model=model, phase_names=phase_names) if phase_names else None
    ticket = (
        write_ticket(transcript, values=values, model=model, rubric_id=rubric.id, rubric_roles=tuple(rubric.roles))
        if values is not None
        else None
    )
    card = write_deal_card(transcript, interest=interest, model=model) if interest is not None else None
    notes = write_meeting_notes(transcript, model=model) if meeting else None
    steps = [step for step in (classification, synthesis, phases, ticket, card, notes) if step is not None]
    prompts = (*scoring.prompts, *(p for step in steps for p in step.prompts))
    return build_report(
        rubric=rubric,
        transcript=transcript,
        dimensions=scoring.dimensions,
        metrics=scoring.metrics,
        overall=overall,
        synthesis=synthesis,
        calls=(
            *(classification.calls if classification else ()),
            *scoring.calls,
            *(c for step in steps if step is not classification for c in step.calls),
        ),
        prompt_hashes={p.name: p.to_record() for p in prompts},
        classification=classification,
        phases=phases,
        ticket=ticket,
        deal_card=card,
        meeting_notes=notes,
    )
