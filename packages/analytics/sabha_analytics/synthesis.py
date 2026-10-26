"""Overall score and the synthesis call (plan task P5.7, pure parts: no MongoDB, no queue).

Overall score (`compute_overall`):

- The weighted mean of VERIFIED dimensions only, weights as written in the rubric, computed exactly with fractions
  and rounded half up to one decimal (3.25 -> 3.3; Python's round() would give 3.2 on an exact half).
- A dimension verified as not applicable (rubric `not_applicable_when`, for example escalation on a call with
  nothing to escalate) is left out entirely: its weight leaves the total, so the other weights are rescaled. An
  unverified dimension stays in the total (we do not know whether it applied).
- If the verified weight is less than 60% of the applicable weight, there is no overall score: too little of
  the rubric is backed by verified evidence for a number to be fair. The report then asks for review
  (RecordingStatus.NEEDS_REVIEW, reason "low_verification") and the synthesis call is skipped.

Synthesis (`synthesise`, gateway task TASK_SYNTHESIS, the mid tier):

- Built ONLY from verified dimension results (score, rationale, verified quotes) and the computed metrics. The
  transcript is not sent; the model never sees an unverified judgement.
- Output: summary (<= 80 words), strengths (2-3), gaps (2-3), suggestions (exactly 3), each strength, gap and
  suggestion <= 40 words (our limit, so the report stays readable), each suggestion naming one moment by utterance
  id.
- Allowed moments: utterances cited by verified evidence AND spoken by an analysed role (for the teaching rubric,
  the teacher). The prompt lists them; a suggestion pointing anywhere else is refused, distinguishing an unknown
  id, a line not spoken by the analysed staff member, and a staff line that is not among the verified moments.
  Why not student lines (golden rule 10, staff are analysed, not students): a suggestion anchored on a student's
  line makes that student the subject of feedback about their teacher, and with playback and un-redaction it
  would point at a child. The teacher's line just before or after is the moment to work on.
- No placeholder ([STUDENT_1], [PHONE_1], ...) may appear in any synthesis text: un-redacted for an authorised
  viewer it would name a student or show a number in staff feedback.
- An answer that breaks a rule is re-asked once with the specific problems. If the second answer also fails,
  there is no synthesis and the report asks for review (reason "synthesis_failed"). The verified scores are kept;
  nothing unverified is shown.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.scoring import (
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    DimensionResult,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
    normalise_metrics,
    prompt_roles,
    render_metrics,
)
from sabha_analytics.scoring import _check_text as check_text

MIN_VERIFIED_SHARE = Fraction(3, 5)
"""Verified weight / total weight below which there is no overall score."""

LOW_VERIFICATION = "low_verification"
SYNTHESIS_FAILED = "synthesis_failed"

MAX_SUMMARY_WORDS = 80
MAX_ITEM_WORDS = 40
LIST_ITEMS = (2, 3)
"""Allowed number of strengths and of gaps (inclusive)."""
SUGGESTIONS = 3
MAX_MOMENT_CHARS = 300


# --- overall score -----------------------------------------------------------------------------------------------


def _weight(value: float) -> Fraction:
    return Fraction(str(value))  # the decimal as written in the rubric (0.15, not its binary approximation)


@dataclass(frozen=True, slots=True)
class OverallScore:
    score: float | None
    """Weighted mean of verified dimensions to 1 decimal, or None when less than 60% of the weight is verified."""
    verified_weight: float
    total_weight: float
    """The weight of the dimensions that apply (not-applicable ones are left out)."""
    verified_share: float
    """verified_weight / total_weight, rounded to 4 decimals."""

    @property
    def needs_review(self) -> bool:
        return self.score is None


def compute_overall(dimensions: Sequence[DimensionResult]) -> OverallScore:
    """The overall score of a rubric's dimension results (module docstring)."""
    applicable = [d for d in dimensions if not (d.verified and d.not_applicable)]
    total = sum((_weight(dimension.weight) for dimension in applicable), Fraction(0))
    verified = [dimension for dimension in applicable if dimension.verified and dimension.score is not None]
    verified_weight = sum((_weight(dimension.weight) for dimension in verified), Fraction(0))
    share = verified_weight / total if total > 0 else Fraction(0)
    score: float | None = None
    if verified and share >= MIN_VERIFIED_SHARE:
        mean = sum((_weight(d.weight) * (d.score or 0) for d in verified), Fraction(0)) / verified_weight
        score = float(Fraction(int(mean * 10 + Fraction(1, 2)), 10))  # half up; mean is positive
    return OverallScore(score, float(verified_weight), float(total), round(float(share), 4))


# --- synthesis ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Moment:
    """An utterance the synthesis may point a suggestion at."""

    utterance_id: str
    role: str
    start_ms: int
    end_ms: int
    text: str
    """Redacted."""


@dataclass(frozen=True, slots=True)
class Suggestion:
    text: str
    utterance_id: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class Synthesis:
    summary: str
    strengths: tuple[str, ...]
    gaps: tuple[str, ...]
    suggestions: tuple[Suggestion, ...]


@dataclass(frozen=True, slots=True)
class SynthesisOutcome:
    synthesis: Synthesis | None
    attempts: int
    """Model calls made: 0 (nothing to synthesise), 1 or 2."""
    failure_reasons: tuple[str, ...]
    """Problem codes when there is no synthesis; empty otherwise."""
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]
    """Prompts actually sent (empty when no call was made)."""


def allowed_moments(
    dimensions: Sequence[DimensionResult], transcript: PreparedTranscript, analysed_roles: Collection[str]
) -> tuple[Moment, ...]:
    """Utterances cited by verified evidence and spoken by an analysed role, in time order, each once."""
    ids = {
        result.utterance_id
        for dimension in dimensions
        if dimension.verified
        for result in dimension.evidence
        if result.verified and result.utterance_id is not None
    }
    moments = []
    for uid in sorted(ids):
        utterance = transcript.get(uid)
        if utterance is not None and utterance.role in analysed_roles:
            text = " ".join(utterance.text.split())
            if len(text) > MAX_MOMENT_CHARS:
                text = text[: MAX_MOMENT_CHARS - 3] + "..."
            moments.append(Moment(uid, utterance.role, utterance.start_ms, utterance.end_ms, text))
    return tuple(sorted(moments, key=lambda moment: (moment.start_ms, moment.utterance_id)))


def synthesis_output_schema(moments: Sequence[Moment]) -> dict[str, Any]:
    """The JSON Schema of a synthesis answer (given to the gateway for structured output)."""
    text = {"type": "string", "minLength": 1}
    listed = {"type": "array", "minItems": LIST_ITEMS[0], "maxItems": LIST_ITEMS[1], "items": text}
    suggestion = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "utterance_id"],
        "properties": {"text": text, "utterance_id": {"enum": [moment.utterance_id for moment in moments]}},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "strengths", "gaps", "suggestions"],
        "properties": {
            "summary": text,
            "strengths": listed,
            "gaps": listed,
            "suggestions": {"type": "array", "minItems": SUGGESTIONS, "maxItems": SUGGESTIONS, "items": suggestion},
        },
    }


def _check_list(name: str, value: object) -> list[Problem]:
    low, high = LIST_ITEMS
    if not isinstance(value, list) or not low <= len(value) <= high:
        return [Problem("invalid_shape", f"{name} must be a list of {low} to {high} strings.")]
    problems = []
    for number, item in enumerate(value, start=1):
        problems += check_text(f"{name} {number}", item, MAX_ITEM_WORDS)
    return problems


def _check_suggestion(
    number: int,
    item: object,
    transcript: PreparedTranscript,
    moments: Mapping[str, Moment],
    analysed_roles: Collection[str],
) -> list[Problem]:
    where = f"suggestion {number}"
    if not isinstance(item, dict) or set(item) != {"text", "utterance_id"}:
        return [Problem("invalid_shape", f"{where} must be {{text: string, utterance_id: string}}.")]
    problems = check_text(where, item["text"], MAX_ITEM_WORDS)
    uid = item["utterance_id"]
    utterance = transcript.get(uid) if isinstance(uid, str) else None
    if utterance is None:
        problems.append(Problem("unknown_moment", f"{where} refers to {uid!r}, which is not a transcript line."))
    elif utterance.role not in analysed_roles:
        problems.append(
            Problem(
                "not_staff_moment", f"{where} refers to {uid}, which the staff member did not say; use a listed moment."
            )
        )
    elif uid not in moments:
        problems.append(Problem("unlisted_moment", f"{where} refers to {uid}, which is not in the list of moments."))
    return problems


def validate_synthesis(
    data: object,
    transcript: PreparedTranscript,
    moments: Sequence[Moment],
    analysed_roles: Collection[str],
) -> tuple[Synthesis | None, list[Problem]]:
    """Check a synthesis answer (module docstring). Returns the synthesis if there are no problems."""
    keys = {"summary", "strengths", "gaps", "suggestions"}
    if not isinstance(data, dict) or set(data) != keys:
        return None, [
            Problem(
                "invalid_output", "The answer must be one JSON object with exactly " + ", ".join(sorted(keys)) + "."
            )
        ]
    by_id = {moment.utterance_id: moment for moment in moments}
    problems = check_text("summary", data["summary"], MAX_SUMMARY_WORDS)
    problems += _check_list("strengths", data["strengths"])
    problems += _check_list("gaps", data["gaps"])
    suggestions = data["suggestions"]
    if not isinstance(suggestions, list) or len(suggestions) != SUGGESTIONS:
        problems.append(Problem("invalid_shape", f"suggestions must be a list of exactly {SUGGESTIONS} items."))
    else:
        for number, item in enumerate(suggestions, start=1):
            problems += _check_suggestion(number, item, transcript, by_id, analysed_roles)
    if problems:
        return None, problems
    return (
        Synthesis(
            summary=data["summary"],
            strengths=tuple(data["strengths"]),
            gaps=tuple(data["gaps"]),
            suggestions=tuple(
                Suggestion(
                    item["text"],
                    item["utterance_id"],
                    by_id[item["utterance_id"]].start_ms,
                    by_id[item["utterance_id"]].end_ms,
                )
                for item in suggestions
            ),
        ),
        [],
    )


def _render_dimension(dimension: DimensionResult) -> str:
    lines = [
        f"## {dimension.key}: {dimension.name} (score {dimension.score} of 5, weight {dimension.weight})",
        f"Rationale: {dimension.rationale}",
        "Evidence:",
    ]
    lines += [
        f'- {result.utterance_id} (start_ms={result.start_ms}): "{result.matched_text}"'
        for result in dimension.evidence
    ]
    return "\n".join(lines)


def synthesise(
    *,
    rubric_id: str,
    rubric_version: str,
    dimensions: Sequence[DimensionResult],
    metrics: Iterable[Mapping[str, object]],
    transcript: PreparedTranscript,
    model: JudgeModel,
    analysed_roles: Collection[str],
    rubric_roles: Sequence[str] = ("teacher", "students"),
    prompts_dir: Path = PROMPTS_DIR,
) -> SynthesisOutcome:
    """Ask for the summary, strengths, gaps and suggestions from verified results only (module docstring).
    `rubric_roles`: the rubric's (analysed, others) roles, which the system prompt names."""
    roles = frozenset(analysed_roles)
    verified = [d for d in dimensions if d.verified and not d.not_applicable]  # not-applicable ones have no score
    if not verified:
        return SynthesisOutcome(None, 0, ("no_verified_dimensions",), (), ())
    moments = allowed_moments(verified, transcript, roles)
    if not moments:
        return SynthesisOutcome(None, 0, ("no_moments",), (), ())
    system_prompt = load_prompt("synthesis.system", prompts_dir)
    request_prompt = load_prompt("synthesis.request", prompts_dir)
    system = system_prompt.render(**prompt_roles(rubric_id, rubric_roles))
    prefix = request_prompt.render(
        rubric_id=rubric_id,
        rubric_version=rubric_version,
        dimensions="\n\n".join(_render_dimension(dimension) for dimension in verified),
        metrics=render_metrics(normalise_metrics(metrics)),
        moments="\n".join(
            f'- {moment.utterance_id} (start_ms={moment.start_ms}): "{moment.text}"' for moment in moments
        ),
    )
    calls: list[CallRecord] = []
    schema = synthesis_output_schema(moments)
    problems: list[Problem] = []
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system,
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=schema,
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        synthesis, problems = validate_synthesis(data, transcript, moments, roles)
        if synthesis is not None:
            return SynthesisOutcome(synthesis, attempt, (), tuple(calls), (system_prompt, request_prompt))
    codes = tuple(dict.fromkeys(problem.code for problem in problems))
    return SynthesisOutcome(None, 2, codes, tuple(calls), (system_prompt, request_prompt))
