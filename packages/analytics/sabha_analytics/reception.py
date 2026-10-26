"""The ticket for a front-desk conversation: a school's phone call or a business's walk-in visitor (plan task P5.8).

From the redacted transcript the model writes: category, resolution status, follow-up (what still has to happen and
the role of the person who should do it, or null when nothing is left), a ticket summary of at most 60 words, and two
quotes: `need_quote`, where the caller or visitor says what they need (the category and summary rest on it), and
`outcome_quote`, where the conversation reaches its outcome (the status and follow-up rest on it).

- Golden rule 5: both quotes must be found in the transcript (grounding.verify_quote, the same check as rubric
  evidence) and are stored in the transcript's own wording with that utterance's times. A ticket is shown only with
  both; a quote that is not found counts as a failing answer.

- Category and status must be from the rubric's approved lists (`output_values.category` and `.status`, read by
  `ticket_values`), so a tenant's rubric, not code, decides them. The status list must include "resolved".
- A follow-up must be null when the call was resolved, and is required for every other status.
- No placeholder may appear in any text: un-redacted it would put a caller's name or number into a ticket that is
  shared more widely than the recording (golden rule 8).
- A failing answer is re-asked once; after that there is no ticket and the recording asks for review
  ("ticket_failed"). The rubric scores are not affected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.sales import Evidence, QuoteCheck, quoted_item
from sabha_analytics.scoring import (
    PLACEHOLDER,
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    conversation_kind,
    feedback_text,
    load_prompt,
    word_count,
)

RESOLVED = "resolved"
MAX_SUMMARY_WORDS = 60
MAX_FOLLOW_UP_WORDS = 40
MAX_OWNER_ROLE_CHARS = 40
TICKET_FAILED = "ticket_failed"
TICKET_KEYS = ("category", "status", "follow_up", "summary", "need_quote", "outcome_quote")


@dataclass(frozen=True, slots=True)
class TicketValues:
    """The allowed categories and statuses, in the rubric's order."""

    categories: tuple[str, ...]
    statuses: tuple[str, ...]


def ticket_values(output_values: Mapping[str, Sequence[str]] | None) -> TicketValues:
    """The ticket's allowed values from a rubric's `output_values`; ValueError if the rubric cannot make tickets."""
    values = output_values or {}
    missing = [key for key in ("category", "status") if not values.get(key)]
    if missing:
        raise ValueError(f"the rubric has no output_values for {' and '.join(missing)}, so it cannot make tickets")
    if RESOLVED not in values["status"]:
        raise ValueError(f"the rubric's output_values.status must include {RESOLVED!r}")
    return TicketValues(tuple(values["category"]), tuple(values["status"]))


@dataclass(frozen=True, slots=True)
class FollowUp:
    text: str
    owner_role: str


@dataclass(frozen=True, slots=True)
class Ticket:
    category: str
    status: str
    follow_up: FollowUp | None
    summary: str
    need_evidence: Evidence
    outcome_evidence: Evidence

    def to_record(self) -> dict[str, Any]:
        def ev(e: Evidence) -> dict[str, Any]:
            return {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}

        return {
            "category": self.category,
            "status": self.status,
            "follow_up": None
            if self.follow_up is None
            else {"text": self.follow_up.text, "owner_role": self.follow_up.owner_role},
            "summary": self.summary,
            "evidence": {"need": ev(self.need_evidence), "outcome": ev(self.outcome_evidence)},
        }


@dataclass(frozen=True, slots=True)
class TicketOutcome:
    ticket: Ticket | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def ticket_schema(values: TicketValues) -> dict[str, Any]:
    follow_up = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "owner_role"],
        "properties": {"text": {"type": "string", "minLength": 1}, "owner_role": {"type": "string", "minLength": 1}},
    }
    quote = quoted_item({})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [*TICKET_KEYS],
        "properties": {
            "category": {"enum": list(values.categories)},
            "status": {"enum": list(values.statuses)},
            "follow_up": {"anyOf": [{"type": "null"}, follow_up]},  # strict structured outputs allow anyOf, not oneOf
            "summary": {"type": "string", "minLength": 1},
            "need_quote": quote,
            "outcome_quote": quote,
        },
    }


def _text(where: str, value: object, max_words: int) -> list[Problem]:
    if not isinstance(value, str) or not value.strip():
        return [Problem("invalid_shape", f"{where} must be a non-blank string.")]
    problems = []
    if word_count(value) > max_words:
        problems.append(Problem("too_long", f"{where} has {word_count(value)} words; the limit is {max_words}."))
    if PLACEHOLDER.search(value):
        problems.append(Problem("placeholder_in_text", f"{where} contains a placeholder; say 'the caller' instead."))
    return problems


def validate_ticket(
    data: object, values: TicketValues, *, transcript: PreparedTranscript
) -> tuple[Ticket | None, list[Problem]]:
    if not isinstance(data, dict) or set(data) != set(TICKET_KEYS):
        return None, [Problem("invalid_output", f"Answer with exactly {', '.join(TICKET_KEYS)}.")]
    problems: list[Problem] = []
    quotes = QuoteCheck(transcript)
    found: dict[str, Evidence | None] = {}
    for key in ("need_quote", "outcome_quote"):
        if isinstance(data[key], dict):
            found[key] = quotes.evidence(key, data[key])
        else:
            found[key] = None
            problems.append(Problem("invalid_shape", f"{key} must be {{quote, start_ms, utterance_id}}."))
    need, outcome = found["need_quote"], found["outcome_quote"]
    problems += quotes.problems
    if data["category"] not in values.categories:
        problems.append(Problem("invalid_category", f"category must be one of {', '.join(values.categories)}."))
    if data["status"] not in values.statuses:
        problems.append(Problem("invalid_status", f"status must be one of {', '.join(values.statuses)}."))
    problems += _text("summary", data["summary"], MAX_SUMMARY_WORDS)
    follow_up = data["follow_up"]
    parsed: FollowUp | None = None
    if follow_up is None:
        if data["status"] != RESOLVED:
            problems.append(Problem("missing_follow_up", f"a call that is not {RESOLVED} needs a follow_up."))
    elif not isinstance(follow_up, dict) or set(follow_up) != {"text", "owner_role"}:
        problems.append(Problem("invalid_shape", "follow_up must be null or {text, owner_role}."))
    else:
        if data["status"] == RESOLVED:
            problems.append(Problem("unexpected_follow_up", "a resolved call has follow_up null."))
        problems += _text("follow_up text", follow_up["text"], MAX_FOLLOW_UP_WORDS)
        role = follow_up["owner_role"]
        if (
            not isinstance(role, str)
            or not role.strip()
            or len(role) > MAX_OWNER_ROLE_CHARS
            or PLACEHOLDER.search(role)
        ):
            problems.append(
                Problem("invalid_owner_role", "owner_role must be a short role name such as 'accounts office'.")
            )
        else:
            parsed = FollowUp(follow_up["text"], role)
    if problems or need is None or outcome is None:
        return None, problems
    return Ticket(data["category"], data["status"], parsed, data["summary"], need, outcome), []


def write_ticket(
    transcript: PreparedTranscript,
    *,
    values: TicketValues,
    model: JudgeModel,
    rubric_id: str,
    rubric_roles: Sequence[str],
    prompts_dir: Path = PROMPTS_DIR,
) -> TicketOutcome:
    """Ask for the conversation's ticket (module docstring). The prompt names the conversation and the other role
    ("caller", "visitor") from the rubric."""
    if len(rubric_roles) < 2:
        raise ValueError("a reception rubric needs two roles: the receptionist and the caller or visitor")
    names = {"conversation": conversation_kind(rubric_id, rubric_roles), "other_role": rubric_roles[1]}
    system_p, request_p = load_prompt("reception.system", prompts_dir), load_prompt("reception.request", prompts_dir)
    prefix = request_p.render(
        categories=", ".join(values.categories), statuses=", ".join(values.statuses), transcript=transcript.render()
    )
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(**names),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=ticket_schema(values),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        ticket, problems = validate_ticket(data, values, transcript=transcript)
        if ticket is not None:
            return TicketOutcome(ticket, attempt, (), tuple(calls), (system_p, request_p))
    return TicketOutcome(None, 2, tuple(dict.fromkeys(p.code for p in problems)), tuple(calls), (system_p, request_p))
