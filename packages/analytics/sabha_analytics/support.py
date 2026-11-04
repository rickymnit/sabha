"""The case card for a support call (support rubric, owner's decision 2026-11-04).

From the redacted transcript the model writes, every item with a quote it rests on:

- product: which of the company's products the call is about, at most 8 words, or null when it is never said;
- problem: the customer's problem in one sentence, at most 30 words, or null when no problem is described;
- steps_tried: up to 5 steps tried, on the call or by the customer before it, each at most 20 words, and who did it
  (support_agent or customer);
- outcome: one of the rubric's `output_values.outcome`, with the quote it rests on ("unclear" needs none);
- follow_up: what was promised next, who does it (support_agent, customer or both) and the date or time as said, or
  null when nothing was promised.

Golden rule 5 applies to every item, exactly as for the deal card (sabha_analytics.sales): its quote must be found
in the transcript and is stored in the transcript's own wording, with that utterance's times. A failing answer is
re-asked once with the problems; after that, items whose quote is still not found are LEFT OUT (counted in
`left_out`), never shown. If the second answer is not valid at all, there is no case card. The rubric scores are not
affected either way, and the recording does not stop for review: the report simply has no card.

No placeholder may appear in the model's own words (golden rule 8); quotes may contain them, as rubric evidence does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.sales import UNCLEAR, Evidence, QuoteCheck, quoted_item
from sabha_analytics.scoring import (
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
)

STEP_BY = ("support_agent", "customer")
OWNERS = ("support_agent", "customer", "both")
MAX_STEPS = 5
MAX_PRODUCT_WORDS = 8
MAX_PROBLEM_WORDS = 30
MAX_STEP_WORDS = 20
MAX_ACTION_WORDS = 30
MAX_DUE_WORDS = 8
_KEYS = frozenset({"product", "problem", "steps_tried", "outcome", "follow_up"})


def outcome_values(output_values: Mapping[str, Sequence[str]] | None) -> tuple[str, ...]:
    """The rubric's outcomes; ValueError if it has none or lacks "unclear"."""
    values = tuple((output_values or {}).get("outcome") or ())
    if not values:
        raise ValueError("the rubric has no output_values.outcome, so it cannot make case cards")
    if UNCLEAR not in values:
        raise ValueError(f"the rubric's output_values.outcome must include {UNCLEAR!r}")
    return values


@dataclass(frozen=True, slots=True)
class Product:
    name: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class CaseProblem:
    problem: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Step:
    step: str
    by: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Outcome:
    value: str
    evidence: Evidence | None  # None only for "unclear"


@dataclass(frozen=True, slots=True)
class FollowUp:
    action: str
    owner: str
    due: str | None
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class CaseCard:
    product: Product | None
    problem: CaseProblem | None
    steps_tried: tuple[Step, ...]
    outcome: Outcome | None  # None when its quote could not be verified
    follow_up: FollowUp | None
    left_out: int = 0  # items dropped because their quote was not found in the transcript

    def to_record(self) -> dict[str, Any]:
        def ev(e: Evidence | None) -> dict[str, Any] | None:
            if e is None:
                return None
            return {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}

        return {
            "product": None
            if self.product is None
            else {"name": self.product.name, "evidence": ev(self.product.evidence)},
            "problem": None
            if self.problem is None
            else {"problem": self.problem.problem, "evidence": ev(self.problem.evidence)},
            "steps_tried": [{"step": s.step, "by": s.by, "evidence": ev(s.evidence)} for s in self.steps_tried],
            "outcome": None
            if self.outcome is None
            else {"value": self.outcome.value, "evidence": ev(self.outcome.evidence)},
            "follow_up": None
            if self.follow_up is None
            else {
                "action": self.follow_up.action,
                "owner": self.follow_up.owner,
                "due": self.follow_up.due,
                "evidence": ev(self.follow_up.evidence),
            },
            "left_out": self.left_out,
        }


@dataclass(frozen=True, slots=True)
class CaseCardOutcome:
    card: CaseCard | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def case_card_schema(outcomes: Sequence[str]) -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    nullable_quote = {
        "quote": {"type": ["string", "null"]},
        "start_ms": {"type": ["integer", "null"], "minimum": 0},
        "utterance_id": {"type": ["string", "null"]},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_KEYS),
        "properties": {
            "product": {"anyOf": [{"type": "null"}, quoted_item({"name": text})]},
            "problem": {"anyOf": [{"type": "null"}, quoted_item({"problem": text})]},
            "steps_tried": {
                "type": "array",
                "maxItems": MAX_STEPS,
                "items": quoted_item({"step": text, "by": {"enum": list(STEP_BY)}}),
            },
            "outcome": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value", *nullable_quote],
                "properties": {"value": {"enum": list(outcomes)}, **nullable_quote},
            },
            "follow_up": {
                "anyOf": [  # strict structured outputs allow anyOf, not oneOf
                    {"type": "null"},
                    quoted_item({"action": text, "owner": {"enum": list(OWNERS)}, "due": {"type": ["string", "null"]}}),
                ]
            },
        },
    }


def validate_case_card(
    data: object, *, transcript: PreparedTranscript, outcomes: Sequence[str]
) -> tuple[CaseCard | None, list[Problem]]:
    """The card (verified items only) and every problem found. The card is None when the answer's shape or texts
    are invalid; quote problems alone still give a card, without those items."""
    if not isinstance(data, dict) or set(data) != _KEYS:
        return None, [Problem("invalid_output", f"Answer with exactly {', '.join(sorted(_KEYS))}.")]
    check = QuoteCheck(transcript)
    steps = data["steps_tried"]
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        return None, [Problem("invalid_shape", f"steps_tried is a list of at most {MAX_STEPS}.")]

    product: Product | None = None
    if (raw := data["product"]) is not None:
        if not isinstance(raw, dict):
            check.problems.append(Problem("invalid_shape", "product must be null or {name, quote...}."))
        else:
            name = check.text("product", raw.get("name"), MAX_PRODUCT_WORDS)
            ev = check.evidence("product", raw)
            product = Product(name, ev) if name is not None and ev is not None else None

    problem: CaseProblem | None = None
    if (raw := data["problem"]) is not None:
        if not isinstance(raw, dict):
            check.problems.append(Problem("invalid_shape", "problem must be null or {problem, quote...}."))
        else:
            what = check.text("problem", raw.get("problem"), MAX_PROBLEM_WORDS)
            ev = check.evidence("problem", raw)
            problem = CaseProblem(what, ev) if what is not None and ev is not None else None

    kept_steps = []
    for i, item in enumerate(steps, 1):
        if not isinstance(item, dict) or item.get("by") not in STEP_BY:
            check.problems.append(Problem("invalid_shape", f"step {i} needs a step, by (support_agent or customer)."))
            continue
        step = check.text(f"step {i}", item.get("step"), MAX_STEP_WORDS)
        ev = check.evidence(f"step {i}", item)
        if step is not None and ev is not None:
            kept_steps.append(Step(step, item["by"], ev))

    outcome: Outcome | None = None
    raw = data["outcome"]
    allowed = tuple(outcomes)
    if not isinstance(raw, dict) or raw.get("value") not in allowed:
        check.problems.append(Problem("invalid_shape", f"outcome.value must be one of {', '.join(allowed)}."))
    elif raw["value"] == UNCLEAR and raw.get("quote") is None:
        outcome = Outcome(UNCLEAR, None)
    else:
        ev = check.evidence("outcome", raw)
        outcome = Outcome(raw["value"], ev) if ev is not None else None

    follow_up: FollowUp | None = None
    if (raw := data["follow_up"]) is not None:
        if not isinstance(raw, dict) or raw.get("owner") not in OWNERS:
            check.problems.append(Problem("invalid_shape", "follow_up must be null or {action, owner, due, quote...}."))
        else:
            action = check.text("follow_up action", raw.get("action"), MAX_ACTION_WORDS)
            due = check.text("follow_up due", raw.get("due"), MAX_DUE_WORDS, optional=True)
            ev = check.evidence("follow_up", raw)
            if action is not None and ev is not None:
                follow_up = FollowUp(action, raw["owner"], due, ev)

    blocking = [p for p in check.problems if p.code != "quote_not_found"]
    if blocking:
        return None, check.problems
    card = CaseCard(product, problem, tuple(kept_steps), outcome, follow_up, left_out=check.unverified)
    return card, check.problems


def write_case_card(
    transcript: PreparedTranscript, *, outcomes: Sequence[str], model: JudgeModel, prompts_dir: Path = PROMPTS_DIR
) -> CaseCardOutcome:
    """Ask for the call's case card (module docstring)."""
    system_p, request_p = load_prompt("case_card.system", prompts_dir), load_prompt("case_card.request", prompts_dir)
    prefix = request_p.render(outcomes=", ".join(outcomes), transcript=transcript.render())
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    card: CaseCard | None = None
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=case_card_schema(outcomes),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        card, problems = validate_case_card(data, transcript=transcript, outcomes=outcomes)
        if card is not None and not problems:
            return CaseCardOutcome(card, attempt, (), tuple(calls), (system_p, request_p))
    reasons = tuple(dict.fromkeys(p.code for p in problems))
    return CaseCardOutcome(card, 2, reasons, tuple(calls), (system_p, request_p))
