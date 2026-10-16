"""Conversation-type and language classification (plan task P5.8, small tier).

Used when the uploader did not set the conversation type, or set it with low confidence. The model sees only the
first three minutes of the REDACTED transcript (golden rule 8) and answers {type, language_mix, confidence}.

- `type` must be one of the tenant's enabled types; `language_mix` one of english, hindi, hinglish; `confidence` a
  number from 0 to 1. A malformed answer is re-asked once with the specific problems, then gives up.
- Confidence below MIN_CONFIDENCE (0.7), or no valid answer after two attempts, means the recording needs review
  with reason "uncertain_type": the analysis does not guess which rubric to apply.
- The confidence is the model's own judgement, not a measured probability (golden rule 6); the threshold should be
  checked against reviewed recordings before relying on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.scoring import (
    PROMPTS_DIR,
    CallRecord,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
)

TASK_CLASSIFY = "analysis.classify"
"""Gateway task name (small tier)."""
MIN_CONFIDENCE = 0.7
WINDOW_MS = 180_000
LANGUAGE_MIXES = ("english", "hindi", "hinglish")
UNCERTAIN_TYPE = "uncertain_type"


@dataclass(frozen=True, slots=True)
class Classification:
    type: str | None
    language_mix: str | None
    confidence: float | None
    needs_review_reason: str | None
    """UNCERTAIN_TYPE when the type should not be trusted; None otherwise."""
    attempts: int
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def needs_classification(set_type: str | None, set_type_confidence: float | None) -> bool:
    """True when the uploader gave no type, or gave one with confidence below MIN_CONFIDENCE."""
    return set_type is None or (set_type_confidence is not None and set_type_confidence < MIN_CONFIDENCE)


def opening(transcript: PreparedTranscript, window_ms: int = WINDOW_MS) -> str:
    """The redacted lines that start within the first `window_ms` of the recording."""
    lines = [u for u in transcript.utterances if u.start_ms < window_ms]
    return "\n".join(f"[{u.id} start_ms={u.start_ms}] {' '.join(u.text.split())}" for u in lines)


def classification_schema(types: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "language_mix", "confidence"],
        "properties": {
            "type": {"enum": list(types)},
            "language_mix": {"enum": list(LANGUAGE_MIXES)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def validate_classification(data: object, types: Sequence[str]) -> tuple[tuple[str, str, float] | None, list[Problem]]:
    if not isinstance(data, dict) or set(data) != {"type", "language_mix", "confidence"}:
        return None, [Problem("invalid_output", "Answer with exactly {type, language_mix, confidence}.")]
    problems = []
    if data["type"] not in types:
        problems.append(Problem("invalid_type", f"type must be one of {', '.join(types)}."))
    if data["language_mix"] not in LANGUAGE_MIXES:
        problems.append(Problem("invalid_language", f"language_mix must be one of {', '.join(LANGUAGE_MIXES)}."))
    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        problems.append(Problem("invalid_confidence", "confidence must be a number from 0 to 1."))
    if problems:
        return None, problems
    return (data["type"], data["language_mix"], float(confidence)), []


def classify(
    transcript: PreparedTranscript,
    *,
    model: JudgeModel,
    allowed_types: Sequence[str],
    prompts_dir: Path = PROMPTS_DIR,
) -> Classification:
    """Classify the conversation (module docstring). Never raises for a bad answer: it asks for review instead."""
    if not allowed_types:
        raise ValueError("allowed_types must not be empty")
    system_p, request_p = load_prompt("classify.system", prompts_dir), load_prompt("classify.request", prompts_dir)
    prefix = request_p.render(types=", ".join(allowed_types), transcript=opening(transcript))
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_CLASSIFY,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=classification_schema(allowed_types),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        result, problems = validate_classification(data, allowed_types)
        if result is not None:
            kind, mix, confidence = result
            reason = UNCERTAIN_TYPE if confidence < MIN_CONFIDENCE else None
            return Classification(kind, mix, confidence, reason, attempt, tuple(calls), (system_p, request_p))
    return Classification(None, None, None, UNCERTAIN_TYPE, 2, tuple(calls), (system_p, request_p))
