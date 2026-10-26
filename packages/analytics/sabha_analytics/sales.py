"""The deal card for an in-person sales meeting (sales rubric, owner's decision 2026-10-24).

From the redacted transcript the model writes, every item with a quote it rests on:

- customer_needs: up to 5 needs the customer side stated, each at most 20 words;
- objections: up to 5 concerns the customer raised, how the rep answered (at most 30 words) and whether the
  customer seemed satisfied ("yes", "no" or "unclear", judged only from what was said);
- interest_level: one of the rubric's `output_values.interest_level`, with the quote it rests on ("unclear" needs
  none);
- next_step: the agreed action, who does it (sales_rep, customer or both) and the date or time as said, or null
  when nothing was agreed.

Golden rule 5 applies to every item: its quote must be found in the transcript (grounding.verify_quote, the same
check as rubric evidence) and is stored in the transcript's own wording, with that utterance's times. A failing
answer is re-asked once with the problems; after that, items whose quote is still not found are LEFT OUT (counted in
`left_out`), never shown. If the second answer is not valid at all, there is no deal card. The rubric scores are not
affected either way, and the recording does not stop for review: the report simply has no card.

No placeholder may appear in the model's own words (golden rule 8); quotes may contain them, as rubric evidence does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript, verify_quote
from sabha_analytics.scoring import (
    PLACEHOLDER,
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
    word_count,
)

UNCLEAR = "unclear"
SETTLED_VALUES = ("yes", "no", UNCLEAR)
OWNERS = ("sales_rep", "customer", "both")
MAX_ITEMS = 5
MAX_NEED_WORDS = 20
MAX_OBJECTION_WORDS = 20
MAX_RESPONSE_WORDS = 30
MAX_ACTION_WORDS = 30
MAX_DUE_WORDS = 8


def interest_values(output_values: Mapping[str, Sequence[str]] | None) -> tuple[str, ...]:
    """The rubric's interest levels; ValueError if it has none or lacks "unclear"."""
    values = tuple((output_values or {}).get("interest_level") or ())
    if not values:
        raise ValueError("the rubric has no output_values.interest_level, so it cannot make deal cards")
    if UNCLEAR not in values:
        raise ValueError(f"the rubric's output_values.interest_level must include {UNCLEAR!r}")
    return values


@dataclass(frozen=True, slots=True)
class Evidence:
    quote: str  # the transcript's own (redacted) wording
    utterance_id: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class Need:
    need: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Objection:
    objection: str
    response: str
    settled: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class Interest:
    value: str
    evidence: Evidence | None  # None only for "unclear"


@dataclass(frozen=True, slots=True)
class NextStep:
    action: str
    owner: str
    due: str | None
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class DealCard:
    customer_needs: tuple[Need, ...]
    objections: tuple[Objection, ...]
    interest: Interest | None  # None when its quote could not be verified
    next_step: NextStep | None
    left_out: int = 0  # items dropped because their quote was not found in the transcript

    def to_record(self) -> dict[str, Any]:
        def ev(e: Evidence | None) -> dict[str, Any] | None:
            if e is None:
                return None
            return {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}

        return {
            "customer_needs": [{"need": n.need, "evidence": ev(n.evidence)} for n in self.customer_needs],
            "objections": [
                {"objection": o.objection, "response": o.response, "settled": o.settled, "evidence": ev(o.evidence)}
                for o in self.objections
            ],
            "interest_level": None
            if self.interest is None
            else {"value": self.interest.value, "evidence": ev(self.interest.evidence)},
            "next_step": None
            if self.next_step is None
            else {
                "action": self.next_step.action,
                "owner": self.next_step.owner,
                "due": self.next_step.due,
                "evidence": ev(self.next_step.evidence),
            },
            "left_out": self.left_out,
        }


@dataclass(frozen=True, slots=True)
class DealCardOutcome:
    card: DealCard | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


_QUOTE = {
    "quote": {"type": "string", "minLength": 1},
    "start_ms": {"type": "integer", "minimum": 0},
    "utterance_id": {"type": "string", "minLength": 1},
}


def _item(fields: Mapping[str, Any]) -> dict[str, Any]:
    properties = {**fields, **_QUOTE}
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def deal_card_schema(interest: Sequence[str]) -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    nullable_quote = {
        "quote": {"type": ["string", "null"]},
        "start_ms": {"type": ["integer", "null"], "minimum": 0},
        "utterance_id": {"type": ["string", "null"]},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["customer_needs", "objections", "interest_level", "next_step"],
        "properties": {
            "customer_needs": {"type": "array", "maxItems": MAX_ITEMS, "items": _item({"need": text})},
            "objections": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": _item({"objection": text, "response": text, "settled": {"enum": list(SETTLED_VALUES)}}),
            },
            "interest_level": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value", *nullable_quote],
                "properties": {"value": {"enum": list(interest)}, **nullable_quote},
            },
            "next_step": {
                "anyOf": [  # strict structured outputs allow anyOf, not oneOf
                    {"type": "null"},
                    _item({"action": text, "owner": {"enum": list(OWNERS)}, "due": {"type": ["string", "null"]}}),
                ]
            },
        },
    }


@dataclass
class _Check:
    """Validates one answer: shape problems block it; quote problems are fed back and the items are left out."""

    transcript: PreparedTranscript
    interest: Sequence[str]
    problems: list[Problem] = field(default_factory=list)
    unverified: int = 0

    def text(self, where: str, value: object, max_words: int, *, optional: bool = False) -> str | None:
        if value is None and optional:
            return None
        if not isinstance(value, str) or not value.strip():
            self.problems.append(Problem("invalid_shape", f"{where} must be a non-blank string."))
            return None
        if word_count(value) > max_words:
            self.problems.append(
                Problem("too_long", f"{where} has {word_count(value)} words; the limit is {max_words}.")
            )
        if PLACEHOLDER.search(value):
            self.problems.append(
                Problem("placeholder_in_text", f"{where} contains a placeholder; say 'the customer' instead.")
            )
        return value

    def evidence(self, where: str, item: Mapping[str, Any]) -> Evidence | None:
        quote, start, uid = item.get("quote"), item.get("start_ms"), item.get("utterance_id")
        if not isinstance(quote, str) or not isinstance(start, int) or isinstance(start, bool):
            self.problems.append(Problem("invalid_shape", f"{where} needs a quote and its start_ms."))
            return None
        found = verify_quote(self.transcript, quote, start_ms=start, utterance_id=uid if isinstance(uid, str) else None)
        if not found.verified or found.utterance_id is None or found.matched_text is None:
            self.unverified += 1
            self.problems.append(Problem(
                "quote_not_found",
                f"{where}: the quote {quote!r} was not found in the transcript near {start} ms ({found.reason}). "
                "Quote the transcript word for word, at least three words, with the start_ms of its utterance.",
            ))  # fmt: skip
            return None
        utterance = self.transcript.get(found.utterance_id)
        if utterance is None:  # cannot happen: verify_quote only returns ids from this transcript
            return None
        return Evidence(found.matched_text, utterance.id, utterance.start_ms, utterance.end_ms)


def validate_deal_card(
    data: object, *, transcript: PreparedTranscript, interest: Sequence[str]
) -> tuple[DealCard | None, list[Problem]]:
    """The card (verified items only) and every problem found. The card is None when the answer's shape or texts
    are invalid; quote problems alone still give a card, without those items."""
    keys = {"customer_needs", "objections", "interest_level", "next_step"}
    if not isinstance(data, dict) or set(data) != keys:
        return None, [Problem("invalid_output", f"Answer with exactly {', '.join(sorted(keys))}.")]
    check = _Check(transcript, interest)
    needs, objections = data["customer_needs"], data["objections"]
    if not isinstance(needs, list) or not isinstance(objections, list) or max(len(needs), len(objections)) > MAX_ITEMS:
        return None, [Problem("invalid_shape", f"customer_needs and objections are lists of at most {MAX_ITEMS}.")]

    kept_needs = []
    for i, item in enumerate(needs, 1):
        text = check.text(f"need {i}", item.get("need") if isinstance(item, dict) else None, MAX_NEED_WORDS)
        ev = check.evidence(f"need {i}", item) if isinstance(item, dict) else None
        if text is not None and ev is not None:
            kept_needs.append(Need(text, ev))
    kept_objections = []
    for i, item in enumerate(objections, 1):
        if not isinstance(item, dict):
            check.problems.append(Problem("invalid_shape", f"objection {i} must be an object."))
            continue
        what = check.text(f"objection {i}", item.get("objection"), MAX_OBJECTION_WORDS)
        response = check.text(f"objection {i} response", item.get("response"), MAX_RESPONSE_WORDS)
        if item.get("settled") not in SETTLED_VALUES:
            check.problems.append(Problem("invalid_shape", f"objection {i} settled must be yes, no or unclear."))
        ev = check.evidence(f"objection {i}", item)
        if what is not None and response is not None and ev is not None and item.get("settled") in SETTLED_VALUES:
            kept_objections.append(Objection(what, response, item["settled"], ev))

    level: Interest | None = None
    raw = data["interest_level"]
    allowed = tuple(check.interest)
    if not isinstance(raw, dict) or raw.get("value") not in allowed:
        check.problems.append(Problem("invalid_shape", f"interest_level.value must be one of {', '.join(allowed)}."))
    elif raw["value"] == UNCLEAR and raw.get("quote") is None:
        level = Interest(UNCLEAR, None)
    else:
        ev = check.evidence("interest_level", raw)
        level = Interest(raw["value"], ev) if ev is not None else None

    next_step: NextStep | None = None
    step = data["next_step"]
    if step is not None:
        if not isinstance(step, dict) or step.get("owner") not in OWNERS:
            check.problems.append(Problem("invalid_shape", "next_step must be null or {action, owner, due, quote...}."))
        else:
            action = check.text("next_step action", step.get("action"), MAX_ACTION_WORDS)
            due = check.text("next_step due", step.get("due"), MAX_DUE_WORDS, optional=True)
            ev = check.evidence("next_step", step)
            if action is not None and ev is not None:
                next_step = NextStep(action, step["owner"], due, ev)

    blocking = [p for p in check.problems if p.code != "quote_not_found"]
    if blocking:
        return None, check.problems
    card = DealCard(tuple(kept_needs), tuple(kept_objections), level, next_step, left_out=check.unverified)
    return card, check.problems


def write_deal_card(
    transcript: PreparedTranscript, *, interest: Sequence[str], model: JudgeModel, prompts_dir: Path = PROMPTS_DIR
) -> DealCardOutcome:
    """Ask for the meeting's deal card (module docstring)."""
    system_p, request_p = load_prompt("deal_card.system", prompts_dir), load_prompt("deal_card.request", prompts_dir)
    prefix = request_p.render(interest_levels=", ".join(interest), transcript=transcript.render())
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    card: DealCard | None = None
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=deal_card_schema(interest),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        card, problems = validate_deal_card(data, transcript=transcript, interest=interest)
        if card is not None and not problems:
            return DealCardOutcome(card, attempt, (), tuple(calls), (system_p, request_p))
    reasons = tuple(dict.fromkeys(p.code for p in problems))
    return DealCardOutcome(card, 2, reasons, tuple(calls), (system_p, request_p))
