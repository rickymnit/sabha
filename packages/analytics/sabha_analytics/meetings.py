"""Meeting notes for a team meeting (meeting rubric, owner's decision 2026-10-24): the meeting is analysed, never a
person.

From the redacted transcript, which for meetings shows each line's anonymous voice label ("S1"), the model writes,
every item with a quote it rests on:

- decisions: up to 8 decisions said in the meeting, each at most 30 words;
- action_items: up to 10, each with what is to be done (at most 30 words), who as named or described in the meeting
  (a name or a role, at most 6 words; null when nobody was named), the voice label of the person who accepted or
  was given it when that is clear from the transcript (null otherwise), and the date or time as said (or null);
- open_questions: up to 5 questions raised and left open, each at most 30 words.

As for the deal card (sabha_analytics.sales): every quote must be found in the transcript and is stored in the
transcript's own wording with that utterance's times; a failing answer is re-asked once and items whose quote is
still not found are LEFT OUT (counted), never shown; a second invalid answer means no notes, which never stops the
recording. The model's own words are English and carry no placeholder (golden rule 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.sales import Evidence, QuoteCheck, quoted_item
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

MAX_DECISIONS = 8
MAX_ACTIONS = 10
MAX_QUESTIONS = 5
MAX_TEXT_WORDS = 30
MAX_OWNER_WORDS = 6
MAX_DUE_WORDS = 8


@dataclass(frozen=True, slots=True)
class Decision:
    decision: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class ActionItem:
    action: str
    owner: str | None  # as named or described in the meeting
    owner_voice: str | None  # the anonymous voice label, when clear; the app shows the name a user gave that voice
    due: str | None
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    question: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class MeetingNotes:
    decisions: tuple[Decision, ...]
    action_items: tuple[ActionItem, ...]
    open_questions: tuple[OpenQuestion, ...]
    left_out: int = 0

    def to_record(self) -> dict[str, Any]:
        def ev(e: Evidence) -> dict[str, Any]:
            return {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}

        return {
            "decisions": [{"decision": d.decision, "evidence": ev(d.evidence)} for d in self.decisions],
            "action_items": [
                {
                    "action": a.action,
                    "owner": a.owner,
                    "owner_voice": a.owner_voice,
                    "due": a.due,
                    "evidence": ev(a.evidence),
                }
                for a in self.action_items
            ],
            "open_questions": [{"question": q.question, "evidence": ev(q.evidence)} for q in self.open_questions],
            "left_out": self.left_out,
        }


@dataclass(frozen=True, slots=True)
class MeetingNotesOutcome:
    notes: MeetingNotes | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def meeting_notes_schema(voices: list[str]) -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    nullable = {"type": ["string", "null"]}
    voice = {"anyOf": [{"type": "null"}, {"enum": voices}]} if voices else nullable
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decisions", "action_items", "open_questions"],
        "properties": {
            "decisions": {"type": "array", "maxItems": MAX_DECISIONS, "items": quoted_item({"decision": text})},
            "action_items": {
                "type": "array",
                "maxItems": MAX_ACTIONS,
                "items": quoted_item({"action": text, "owner": nullable, "owner_voice": voice, "due": nullable}),
            },
            "open_questions": {"type": "array", "maxItems": MAX_QUESTIONS, "items": quoted_item({"question": text})},
        },
    }


def validate_meeting_notes(
    data: object, *, transcript: PreparedTranscript
) -> tuple[MeetingNotes | None, list[Problem]]:
    """The notes (verified items only) and every problem found; None when the answer's shape or texts are invalid."""
    keys = {"decisions", "action_items", "open_questions"}
    if not isinstance(data, dict) or set(data) != keys:
        return None, [Problem("invalid_output", f"Answer with exactly {', '.join(sorted(keys))}.")]
    lists = {key: data[key] for key in keys}
    limits = {"decisions": MAX_DECISIONS, "action_items": MAX_ACTIONS, "open_questions": MAX_QUESTIONS}
    if any(not isinstance(value, list) or len(value) > limits[key] for key, value in lists.items()):
        return None, [Problem("invalid_shape", "decisions, action_items and open_questions are short lists.")]
    voices = {u.speaker for u in transcript.utterances if u.speaker}
    check = QuoteCheck(transcript)

    decisions = []
    for i, item in enumerate(lists["decisions"], 1):
        if not isinstance(item, dict):
            check.problems.append(Problem("invalid_shape", f"decision {i} must be an object."))
            continue
        text = check.text(f"decision {i}", item.get("decision"), MAX_TEXT_WORDS)
        ev = check.evidence(f"decision {i}", item)
        if text is not None and ev is not None:
            decisions.append(Decision(text, ev))
    actions = []
    for i, item in enumerate(lists["action_items"], 1):
        if not isinstance(item, dict):
            check.problems.append(Problem("invalid_shape", f"action item {i} must be an object."))
            continue
        what = check.text(f"action item {i}", item.get("action"), MAX_TEXT_WORDS)
        owner = check.text(f"action item {i} owner", item.get("owner"), MAX_OWNER_WORDS, optional=True)
        due = check.text(f"action item {i} due", item.get("due"), MAX_DUE_WORDS, optional=True)
        voice = item.get("owner_voice")
        if voice is not None and voice not in voices:
            check.problems.append(
                Problem("invalid_shape", f"action item {i} owner_voice must be a voice label or null.")
            )
            voice = None
        ev = check.evidence(f"action item {i}", item)
        if what is not None and ev is not None:
            actions.append(ActionItem(what, owner, voice, due, ev))
    questions = []
    for i, item in enumerate(lists["open_questions"], 1):
        if not isinstance(item, dict):
            check.problems.append(Problem("invalid_shape", f"open question {i} must be an object."))
            continue
        text = check.text(f"open question {i}", item.get("question"), MAX_TEXT_WORDS)
        ev = check.evidence(f"open question {i}", item)
        if text is not None and ev is not None:
            questions.append(OpenQuestion(text, ev))

    if any(p.code != "quote_not_found" for p in check.problems):
        return None, check.problems
    notes = MeetingNotes(tuple(decisions), tuple(actions), tuple(questions), left_out=check.unverified)
    return notes, check.problems


def write_meeting_notes(
    transcript: PreparedTranscript, *, model: JudgeModel, prompts_dir: Path = PROMPTS_DIR
) -> MeetingNotesOutcome:
    """Ask for the meeting's notes (module docstring)."""
    system_p = load_prompt("meeting_notes.system", prompts_dir)
    request_p = load_prompt("meeting_notes.request", prompts_dir)
    prefix = request_p.render(transcript=transcript.render())
    voices = sorted({u.speaker for u in transcript.utterances if u.speaker})
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    notes: MeetingNotes | None = None
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=meeting_notes_schema(voices),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        notes, problems = validate_meeting_notes(data, transcript=transcript)
        if notes is not None and not problems:
            return MeetingNotesOutcome(notes, attempt, (), tuple(calls), (system_p, request_p))
    reasons = tuple(dict.fromkeys(p.code for p in problems))
    return MeetingNotesOutcome(notes, 2, reasons, tuple(calls), (system_p, request_p))
