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
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
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
) -> AnalysisResult:
    """Assemble and check an analysis@v1 report (module docstring)."""
    reasons: list[str] = []
    if overall.score is None:
        reasons.append(LOW_VERIFICATION)
    elif synthesis is None or synthesis.synthesis is None:
        reasons.append(SYNTHESIS_FAILED)
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
        if not isinstance(dimension["score"], int) or not 1 <= dimension["score"] <= 5:
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
) -> AnalysisResult:
    """Score, compute the overall score, synthesise when there is one, and assemble the report."""
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
        )
    prompts = (*scoring.prompts, *(synthesis.prompts if synthesis else ()))
    return build_report(
        rubric=rubric,
        transcript=transcript,
        dimensions=scoring.dimensions,
        metrics=scoring.metrics,
        overall=overall,
        synthesis=synthesis,
        calls=(*scoring.calls, *(synthesis.calls if synthesis else ())),
        prompt_hashes={p.name: p.to_record() for p in prompts},
    )
