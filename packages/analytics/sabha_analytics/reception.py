"""The ticket for a front-desk call (plan task P5.8, reception output).

From the redacted transcript the model writes: category, resolution status, follow-up (what still has to happen and
the role of the person who should do it, or null when nothing is left) and a ticket summary of at most 60 words.

- Category and status must be from the allowed values (CATEGORIES, STATUSES, from plan task P5.8).
- A follow-up is required when the status is pending or escalated, and must be null when the call was resolved.
- No placeholder may appear in any text: un-redacted it would put a caller's name or number into a ticket that is
  shared more widely than the recording (golden rule 8).
- A failing answer is re-asked once; after that there is no ticket and the recording asks for review
  ("ticket_failed"). The rubric scores are not affected.

Note: the v0.1 reception rubric draft proposes slightly different category and status lists; they must be settled
with the front-office lead before the reception rubric v1.0 is published (P5.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
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

CATEGORIES = ("complaint", "information", "fee", "admission", "other")
STATUSES = ("resolved", "pending", "escalated")
MAX_SUMMARY_WORDS = 60
MAX_FOLLOW_UP_WORDS = 40
MAX_OWNER_ROLE_CHARS = 40
TICKET_FAILED = "ticket_failed"


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


@dataclass(frozen=True, slots=True)
class TicketOutcome:
    ticket: Ticket | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def ticket_schema() -> dict[str, Any]:
    follow_up = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text", "owner_role"],
        "properties": {"text": {"type": "string", "minLength": 1}, "owner_role": {"type": "string", "minLength": 1}},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "status", "follow_up", "summary"],
        "properties": {
            "category": {"enum": list(CATEGORIES)},
            "status": {"enum": list(STATUSES)},
            "follow_up": {"oneOf": [{"type": "null"}, follow_up]},
            "summary": {"type": "string", "minLength": 1},
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


def validate_ticket(data: object) -> tuple[Ticket | None, list[Problem]]:
    keys = {"category", "status", "follow_up", "summary"}
    if not isinstance(data, dict) or set(data) != keys:
        return None, [Problem("invalid_output", "Answer with exactly category, status, follow_up and summary.")]
    problems: list[Problem] = []
    if data["category"] not in CATEGORIES:
        problems.append(Problem("invalid_category", f"category must be one of {', '.join(CATEGORIES)}."))
    if data["status"] not in STATUSES:
        problems.append(Problem("invalid_status", f"status must be one of {', '.join(STATUSES)}."))
    problems += _text("summary", data["summary"], MAX_SUMMARY_WORDS)
    follow_up = data["follow_up"]
    parsed: FollowUp | None = None
    if follow_up is None:
        if data["status"] in ("pending", "escalated"):
            problems.append(Problem("missing_follow_up", "a pending or escalated call needs a follow_up."))
    elif not isinstance(follow_up, dict) or set(follow_up) != {"text", "owner_role"}:
        problems.append(Problem("invalid_shape", "follow_up must be null or {text, owner_role}."))
    else:
        if data["status"] == "resolved":
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
    if problems:
        return None, problems
    return Ticket(data["category"], data["status"], parsed, data["summary"]), []


def write_ticket(
    transcript: PreparedTranscript, *, model: JudgeModel, prompts_dir: Path = PROMPTS_DIR
) -> TicketOutcome:
    """Ask for the call's ticket (module docstring)."""
    system_p, request_p = load_prompt("reception.system", prompts_dir), load_prompt("reception.request", prompts_dir)
    prefix = request_p.render(
        categories=", ".join(CATEGORIES), statuses=", ".join(STATUSES), transcript=transcript.render()
    )
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=ticket_schema(),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        ticket, problems = validate_ticket(data)
        if ticket is not None:
            return TicketOutcome(ticket, attempt, (), tuple(calls), (system_p, request_p))
    return TicketOutcome(None, 2, tuple(dict.fromkeys(p.code for p in problems)), tuple(calls), (system_p, request_p))
