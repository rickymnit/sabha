"""Meeting notes, with the fake judge: decisions, action items and open questions, each on a verified quote, and a
meeting scored as a whole."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.meetings import validate_meeting_notes, write_meeting_notes
from sabha_analytics.phases import DEFAULT_PHASES
from sabha_analytics.report import analyse, load_report_schema
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_core.state import RecordingStatus

ROWS = (
    ("S0", 0, 8_000, "Aaj teen points: Diwali campaign ka budget, naya hire, aur vendor issue."),
    ("S1", 8_500, 20_000, "Budget ke liye mera suggestion hai do lakh, sirf Instagram aur WhatsApp pe."),
    ("S0", 20_500, 26_000, "Theek hai, toh decide hua budget do lakh, Instagram aur WhatsApp."),
    ("S2", 26_500, 34_000, "Vendor wala issue main dekh leti hoon, kal baarah baje tak call kar dungi."),
    ("S0", 34_500, 42_000, "Naya hire kab tak chahiye, yeh abhi clear nahi hai, next week dekhte hain."),
)


def meeting_document() -> dict[str, Any]:
    return {
        "version": "transcript@v1", "timeline": "original", "asr_model": "fake-asr@1",
        "word_count": sum(len(t.split()) for *_, t in ROWS),
        "utterances": [{"role": "participant", "speaker_label": v, "start_ms": s, "end_ms": e, "text": t,
                        "avg_confidence": 0.9, "low_confidence_spans": []} for v, s, e, t in ROWS],
    }  # fmt: skip


@pytest.fixture
def meeting() -> PreparedTranscript:
    return prepare_transcript(meeting_document(), show_speakers=True)


@pytest.fixture
def meeting_rubric() -> Rubric:
    rubric, _ = load_rubric(Path(__file__).parent / "fixtures" / "rubrics" / "meeting.testing.v1.0.yaml")
    return rubric


NOTES: dict[str, Any] = {
    "decisions": [{"decision": "The Diwali campaign budget is Rs 2 lakh, on Instagram and WhatsApp only.",
                   "quote": "decide hua budget do lakh", "start_ms": 20_500, "utterance_id": "u0002"}],
    "action_items": [{"action": "Call the vendor about the open issue.", "owner": "the person who took it",
                      "owner_voice": "S2", "due": "tomorrow 12 noon", "quote": "kal baarah baje tak call kar dungi",
                      "start_ms": 26_500, "utterance_id": "u0003"}],
    "open_questions": [{"question": "When is the new hire needed?", "quote": "Naya hire kab tak chahiye",
                        "start_ms": 34_500, "utterance_id": "u0004"}],
}  # fmt: skip
SCORES: dict[str, Any] = {
    "dimensions": [
        {"key": "decisions_made", "score": 4, "rationale": "The budget decision is said out loud.",
         "evidence": [{"quote": "decide hua budget do lakh", "utterance_id": "u0002", "start_ms": 20_500}]},
        {"key": "actions_assigned", "score": 3, "rationale": "One action has an owner and a time.",
         "evidence": [{"quote": "kal baarah baje tak call kar dungi", "utterance_id": "u0003",
                       "start_ms": 26_500}]},
    ]
}  # fmt: skip
SYNTHESIS: dict[str, Any] = {
    "summary": "A short meeting that settled the campaign budget and gave out one action.",
    "strengths": ["The budget decision is said clearly.", "The vendor action has a time."],
    "gaps": ["The hiring question was left open.", "Actions were not read back."],
    "suggestions": [
        {"text": "Read the decisions back before moving on.", "utterance_id": "u0002"},
        {"text": "Agree a date when work is taken on.", "utterance_id": "u0003"},
        {"text": "Close by listing who does what.", "utterance_id": "u0003"},
    ],
}
PHASES: dict[str, Any] = {
    "phases": [
        {"phase": "opening", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
        {"phase": "discussion", "start_utterance_id": "u0001", "end_utterance_id": "u0001"},
        {"phase": "decisions", "start_utterance_id": "u0002", "end_utterance_id": "u0003"},
        {"phase": "close", "start_utterance_id": "u0004", "end_utterance_id": "u0004"},
    ]
}
METRICS = [{"key": "voice_count", "value": 3, "unit": "count", "definition": "Voices that spoke."}]


def test_a_meeting_report_has_verified_notes_and_judges_the_meeting(
    meeting_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, NOTES])
    result = analyse(rubric=meeting_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"participant"}, phase_names=DEFAULT_PHASES["meeting"], meeting=True)  # fmt: skip
    report = result.report
    jsonschema.validate(report, load_report_schema())
    assert result.next_status is RecordingStatus.COMPLETED
    notes = report["meeting_notes"]
    (action,) = notes["action_items"]
    assert (action["owner_voice"], action["due"]) == ("S2", "tomorrow 12 noon")
    assert action["evidence"]["start_ms"] == 26_500 and notes["left_out"] == 0
    assert notes["open_questions"][0]["question"] == "When is the new hire needed?"
    scoring_system = model.calls[0]["system"]
    assert "team meeting" in scoring_system and "never score, rank, praise or criticise" in scoring_system.lower()
    assert "participant S2]" in model.calls[-1]["messages"][0]["content"]  # the notes see who said what


def test_an_owner_voice_that_did_not_speak_and_an_invented_quote_are_not_kept(
    meeting: PreparedTranscript, fake_judge: Any
) -> None:
    ghost = {**NOTES["action_items"][0], "owner_voice": "S9"}
    _, problems = validate_meeting_notes({**NOTES, "action_items": [ghost]}, transcript=meeting)
    assert "invalid_shape" in {p.code for p in problems}
    invented = {"decision": "Hire two interns.", "quote": "do interns hire karenge", "start_ms": 34_500,
                "utterance_id": "u0004"}  # fmt: skip
    answer = {**NOTES, "decisions": [*NOTES["decisions"], invented]}
    outcome = write_meeting_notes(meeting, model=fake_judge([answer, answer]))
    assert outcome.notes is not None and outcome.notes.left_out == 1
    assert [d.decision for d in outcome.notes.decisions] == [NOTES["decisions"][0]["decision"]]


def test_no_voice_labels_outside_meetings() -> None:
    lesson = prepare_transcript(meeting_document())
    assert "S2]" not in lesson.render()  # lessons and calls never show who spoke, only the role
