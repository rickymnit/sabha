"""Phases of a conversation for the report timeline (plan task P5.8, small tier).

The model splits the redacted transcript into the phases named for the conversation type, giving each phase's first
and last utterance id. Every boundary is checked against the transcript before it is kept:

- phase names come from the given list, each at most once, in the list's order (a phase that did not happen is left
  out);
- both ids exist, the first line is not after the last, and phases follow each other without overlapping;
- times are taken from the transcript (the first line's start, the last line's end, on the ORIGINAL timeline), never
  from the model.

A failing answer is re-asked once with the specific problems; after that the report simply has no phases (the
timeline is still drawn, without phase labels). Phases are descriptive only and never affect a score.

Default phase lists (P5.8) are used until the rubric files carry their own `phases`.
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

TASK_SEGMENT = "analysis.segment"
"""Gateway task name (small tier)."""

DEFAULT_PHASES: dict[str, tuple[str, ...]] = {
    "teaching": ("introduction", "explanation", "guided_practice", "closing"),
    "reception": ("greeting", "need", "information", "resolution", "close"),
}


@dataclass(frozen=True, slots=True)
class Phase:
    name: str
    start_utterance_id: str
    end_utterance_id: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class PhaseOutcome:
    phases: tuple[Phase, ...] | None
    """None when no valid answer came after two attempts."""
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def phases_schema(names: Sequence[str]) -> dict[str, Any]:
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["phase", "start_utterance_id", "end_utterance_id"],
        "properties": {
            "phase": {"enum": list(names)},
            "start_utterance_id": {"type": "string", "pattern": "^u[0-9]{4,}$"},
            "end_utterance_id": {"type": "string", "pattern": "^u[0-9]{4,}$"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["phases"],
        "properties": {"phases": {"type": "array", "minItems": 1, "maxItems": len(names), "items": item}},
    }


def validate_phases(
    data: object, transcript: PreparedTranscript, names: Sequence[str]
) -> tuple[tuple[Phase, ...] | None, list[Problem]]:
    if (
        not isinstance(data, dict)
        or set(data) != {"phases"}
        or not isinstance(data["phases"], list)
        or not data["phases"]
    ):
        return None, [Problem("invalid_output", 'Answer with {"phases": [...]} and at least one phase.')]
    problems: list[Problem] = []
    phases: list[Phase] = []
    last_name_index, last_end_index = -1, -1
    for number, item in enumerate(data["phases"], start=1):
        where = f"phase {number}"
        if not isinstance(item, dict) or set(item) != {"phase", "start_utterance_id", "end_utterance_id"}:
            problems.append(
                Problem("invalid_shape", f"{where} must be {{phase, start_utterance_id, end_utterance_id}}.")
            )
            continue
        name, first_id, last_id = item["phase"], item["start_utterance_id"], item["end_utterance_id"]
        if name not in names:
            problems.append(Problem("unknown_phase", f"{where}: {name!r} is not one of {', '.join(names)}."))
            continue
        if names.index(name) <= last_name_index:
            problems.append(Problem("phase_order", f"{where}: {name} is repeated or out of order."))
        first = transcript.get(first_id) if isinstance(first_id, str) else None
        last = transcript.get(last_id) if isinstance(last_id, str) else None
        if first is None or last is None:
            problems.append(
                Problem("unknown_utterance", f"{where}: {first_id!r} or {last_id!r} is not a transcript line.")
            )
            continue
        if first.index > last.index:
            problems.append(Problem("reversed", f"{where}: {first_id} comes after {last_id}."))
        if first.index <= last_end_index:
            problems.append(Problem("overlap", f"{where}: starts at {first_id}, inside the previous phase."))
        last_name_index, last_end_index = max(last_name_index, names.index(name)), max(last_end_index, last.index)
        phases.append(Phase(name, first.id, last.id, first.start_ms, last.end_ms))
    if problems:
        return None, problems
    return tuple(phases), []


def segment_phases(
    transcript: PreparedTranscript,
    *,
    model: JudgeModel,
    phase_names: Sequence[str],
    prompts_dir: Path = PROMPTS_DIR,
) -> PhaseOutcome:
    """Ask for the phases and keep them only if every boundary checks out (module docstring)."""
    system_p, request_p = load_prompt("segment.system", prompts_dir), load_prompt("segment.request", prompts_dir)
    prefix = request_p.render(phases=", ".join(phase_names), transcript=transcript.render())
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SEGMENT,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=phases_schema(phase_names),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        phases, problems = validate_phases(data, transcript, phase_names)
        if phases is not None:
            return PhaseOutcome(phases, attempt, (), tuple(calls), (system_p, request_p))
    codes = tuple(dict.fromkeys(p.code for p in problems))
    return PhaseOutcome(None, 2, codes, tuple(calls), (system_p, request_p))
