"""The analyze stage: scores, feedback and the stored report (plan task P5.7; queue llm.analyze).

`work(ctx)`:

1. Reads the transcribe stage's `transcript@v1.json` and the preprocess segment map. Missing: `missing_input`.
2. Finds the rubric (sabha_workers.rubrics; none: `no_rubric`) and prepares the transcript for the LLM: utterance
   ids, and redaction of PII and of the staff member's name pattern (sabha_analytics.grounding; golden rule 8).
3. Computes the metrics in code (sabha_analytics.metrics; golden rule 5: numbers never come from the LLM) and keeps
   the ones the rubric lists.
4. Runs sabha_analytics.report.analyse through the LLM gateway: per-dimension judgements with quotes that the
   grounding verifier must find in the transcript, the overall score from verified dimensions only, synthesis,
   the timeline phases, and for reception the call's ticket. The report is checked against analysis@v1.
5. Stores the report as `analysis@v1.json`, an `analyses` document and one `scores` document per dimension, in one
   transaction. The analysis is keyed by (recording, stage version), so a retried stage replaces its own result
   instead of adding a second one.
6. The report's status decides the end: COMPLETED (the runner moves on and the outbox event starts notify and
   meter), or NEEDS_REVIEW with the report's first review reason (low_verification, synthesis_failed, ...).

LLM failures: retryable ones (rate limits, timeouts, a budget store hiccup) are TransientError; a configuration
problem, an exhausted budget or invalid JSON twice is PermanentError `analysis_failed` with the reason.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sabha_analytics.grounding import prepare_transcript
from sabha_analytics.metrics import compute_metrics, select_metrics
from sabha_analytics.phases import DEFAULT_PHASES
from sabha_analytics.report import analyse
from sabha_analytics.rubric import Rubric
from sabha_analytics.scoring import JudgeModel
from sabha_core.models import Analysis, Person, Score, Tenant
from sabha_core.profiles import ConversationType
from sabha_core.state import RecordingStatus
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap, stats
from sabha_llm.errors import BudgetUnavailableError, LlmError, ProviderError
from sabha_llm.redact import STAFF, KnownName
from sabha_workers.rubrics import NoRubric
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext, TransientError, Work

log = logging.getLogger("sabha.workers.analyze")


@dataclass(frozen=True)
class AnalyzeDeps:
    preprocess_version: str
    transcribe_version: str
    analysis_version: str  # the analyze stage's artefact version: one analysis per (recording, version)
    tenant: Callable[[str], Tenant | None]
    person: Callable[[str, str], Person | None]  # (tenant_id, person_id)
    rubric: Callable[[Tenant, ConversationType], tuple[Rubric, str]]
    judge: Callable[[str, str], JudgeModel]  # (tenant_id, recording_id) -> the LLM, through the gateway
    save: Callable[[str, Analysis, list[Score]], None]  # (tenant_id, analysis, scores), atomically
    llm_cost: Callable[[str, str], float | None]  # (tenant_id, recording_id): cost of this recording's LLM calls


def _get_json(ctx: StageContext, key: str) -> Any:
    try:
        return json.loads(ctx.artefacts.get(key))
    except FileNotFoundError as exc:
        raise PermanentError("missing_input", f"not found: {exc}") from exc


def scores_from(report: dict[str, Any], analysis: Analysis) -> list[Score]:
    return [
        Score(
            analysis_id=analysis.id, recording_id=analysis.recording_id, person_id=analysis.person_id,
            dimension=d["key"], name=d["name"], weight=d["weight"], score=d["score"], verified=d["verified"],
            not_applicable=bool(d.get("not_applicable")), evidence=d["evidence"],
        )
        for d in report["dimensions"]
    ]  # fmt: skip


def make_work(deps: AnalyzeDeps) -> Work:
    """The analyze `work` function for StageRunner (module docstring)."""

    def work(ctx: StageContext) -> dict[str, Any]:
        recording = ctx.recording
        pre = artefact_prefix(ctx.tenant_id, recording.id, "preprocess", deps.preprocess_version)
        asr = artefact_prefix(ctx.tenant_id, recording.id, "transcribe", deps.transcribe_version)
        document = _get_json(ctx, asr + "transcript@v1.json")
        segment_map = SegmentMap.from_json(json.dumps(_get_json(ctx, pre + "segments@v1.json")))
        if recording.duration_ms is None:
            raise PermanentError("missing_input", "the recording has no duration (preprocess did not record it)")
        tenant = deps.tenant(ctx.tenant_id)
        if tenant is None:
            raise PermanentError("missing_input", "the recording's tenant was not found")
        try:
            rubric, rubric_hash = deps.rubric(tenant, recording.type)
        except NoRubric as exc:
            raise PermanentError("no_rubric", str(exc)) from exc

        person = deps.person(ctx.tenant_id, recording.person_id) if recording.person_id else None
        names = [KnownName(person.name, STAFF)] if person is not None else []
        transcript = prepare_transcript(document, names=names)
        metrics = compute_metrics(document, primary_role=rubric.primary_role, segment_map=segment_map,
                                  segment_stats=stats(segment_map, recording.duration_ms),
                                  roles=list(rubric.roles))  # fmt: skip
        selected = select_metrics(metrics, rubric.computed_metrics)
        try:
            result = analyse(
                rubric=rubric, transcript=transcript, metrics=[m.to_record() for m in selected],
                model=deps.judge(ctx.tenant_id, recording.id), analysed_roles={rubric.primary_role},
                phase_names=DEFAULT_PHASES.get(recording.type.value),
                reception=recording.type is ConversationType.RECEPTION,
                sales=recording.type is ConversationType.SALES,
            )  # fmt: skip
        except (ProviderError, BudgetUnavailableError) as exc:
            retryable = isinstance(exc, BudgetUnavailableError) or exc.retryable
            error = TransientError if retryable else PermanentError
            raise error("llm_unavailable" if retryable else "analysis_failed", str(exc)[:500]) from exc
        except LlmError as exc:
            raise PermanentError("analysis_failed", f"{type(exc).__name__}: {str(exc)[:500]}") from exc

        report = result.report
        key = ctx.prefix + "analysis@v1.json"
        ctx.artefacts.put(key, json.dumps(report, ensure_ascii=False).encode(), "application/json")
        usage = report["usage"]["total"]
        analysis = Analysis(
            recording_id=recording.id, version=deps.analysis_version, person_id=recording.person_id,
            unit_id=recording.unit_id, conversation_type=recording.type, rubric_id=rubric.id,
            rubric_version=rubric.version, rubric_hash=rubric_hash, report_key=key, status=report["next_status"],
            overall_score=report["overall"]["score"], verified_share=report["overall"]["verified_share"],
            review_reasons=report["review_reasons"], model_ids=report["model_ids"],
            prompt_hashes={name: p["sha256"] for name, p in report["prompts"].items()},
            usage=usage, cost_usd=deps.llm_cost(ctx.tenant_id, recording.id),
        )  # fmt: skip
        deps.save(ctx.tenant_id, analysis, scores_from(report, analysis))
        meta = {
            "rubric": rubric.id,
            "overall_score": analysis.overall_score,
            "verified_share": analysis.verified_share,
            "dimensions_verified": sum(1 for d in report["dimensions"] if d["verified"]),
            "dimensions": len(report["dimensions"]),
            "llm_calls": len(report["usage"]["calls"]),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cost_usd": analysis.cost_usd,
        }
        log.info("analysed", extra={"recording_id": recording.id, **meta})
        if result.next_status is RecordingStatus.NEEDS_REVIEW:
            reason = report["review_reasons"][0] if report["review_reasons"] else "needs_review"
            raise NeedsReviewError(reason, "the analysis was stored but needs a person to review it")
        return meta

    return work
