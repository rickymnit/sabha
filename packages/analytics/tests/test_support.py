"""The case card for a support call, with the fake judge: every item rests on a verified quote."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.phases import DEFAULT_PHASES
from sabha_analytics.report import analyse, load_report_schema
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_analytics.scoring import group_dimensions
from sabha_analytics.support import outcome_values, validate_case_card, write_case_card
from sabha_core.state import RecordingStatus

CALL_ROWS = (
    ("support_agent", 0, 6_000, "Thank you for calling Brightpath support, main Priya bol rahi hoon."),
    ("customer", 6_500, 15_000, "Fee app mein login ke baad screen band ho jaati hai, maine reinstall bhi kiya."),
    (
        "support_agent",
        15_500,
        30_000,
        "Settings mein jaake cache clear kijiye, phir app kholke batayiye kya dikh raha.",
    ),
    ("customer", 30_500, 36_000, "Haan ab login ho gaya, chal raha hai."),
    ("support_agent", 36_500, 45_000, "Aapki complaint number SR-2231 hai, kal tak ek follow up call bhi aayega."),
)
OUTCOMES = ("solved", "follow_up", "escalated", "not_solved", "unclear")
CARD: dict[str, Any] = {
    "product": {"name": "Fee app", "quote": "Fee app mein login", "start_ms": 6_500, "utterance_id": "u0001"},
    "problem": {"problem": "The app closes right after login.", "quote": "login ke baad screen band ho jaati hai",
                "start_ms": 6_500, "utterance_id": "u0001"},
    "steps_tried": [
        {"step": "Reinstalled the app.", "by": "customer", "quote": "maine reinstall bhi kiya", "start_ms": 6_500,
         "utterance_id": "u0001"},
        {"step": "Cleared the app cache.", "by": "support_agent", "quote": "Settings mein jaake cache clear kijiye",
         "start_ms": 15_500, "utterance_id": "u0002"},
    ],
    "outcome": {"value": "solved", "quote": "ab login ho gaya", "start_ms": 30_500, "utterance_id": "u0003"},
    "follow_up": {"action": "A follow-up call to check the app.", "owner": "support_agent", "due": "tomorrow",
                  "quote": "kal tak ek follow up call bhi aayega", "start_ms": 36_500, "utterance_id": "u0004"},
}  # fmt: skip
SCORES: dict[str, Any] = {
    "dimensions": [
        {"key": "opening_and_verification", "score": 3, "rationale": "Greets with the name but confirms nothing.",
         "evidence": [{"quote": "Thank you for calling Brightpath support", "utterance_id": "u0000", "start_ms": 0}]},
        {"key": "empathy_and_clarity", "score": 3, "rationale": "Polite and plain, with no word for the trouble.",
         "evidence": [{"quote": "phir app kholke batayiye kya dikh raha", "utterance_id": "u0002", "start_ms": 15_500},
                      {"quote": "Aapki complaint number SR-2231 hai", "utterance_id": "u0004", "start_ms": 36_500}]},
        {"key": "holds", "score": None, "rationale": "The customer is never put on hold.",
         "evidence": [{"quote": "Haan ab login ho gaya", "utterance_id": "u0003", "start_ms": 30_500}]},
        {"key": "closing", "score": 2, "rationale": "No summary and no question about anything else.",
         "evidence": [{"quote": "kal tak ek follow up call bhi aayega", "utterance_id": "u0004", "start_ms": 36_500}]},
        {"key": "problem_understood", "score": 3, "rationale": "The customer describes the problem unprompted.",
         "evidence": [{"quote": "login ke baad screen band ho jaati hai", "utterance_id": "u0001", "start_ms": 6_500}]},
        {"key": "troubleshooting", "score": 4, "rationale": "A specific step, and the agent asks for the result.",
         "evidence": [{"quote": "Settings mein jaake cache clear kijiye", "utterance_id": "u0002", "start_ms": 15_500},
                      {"quote": "phir app kholke batayiye kya dikh raha", "utterance_id": "u0002",
                       "start_ms": 15_500}]},
        {"key": "resolution_and_ownership", "score": 4, "rationale": "Solved, with a reference number.",
         "evidence": [{"quote": "Aapki complaint number SR-2231 hai", "utterance_id": "u0004", "start_ms": 36_500}]},
    ]
}  # fmt: skip
SYNTHESIS: dict[str, Any] = {
    "summary": "A short call that fixed a login problem and left a reference number.",
    "strengths": ["Gives one specific step.", "Leaves a reference number."],
    "gaps": ["Asks nothing about the problem.", "Does not sum up at the end."],
    "suggestions": [
        {"text": "Ask since when the problem happens before giving a step.", "utterance_id": "u0002"},
        {"text": "Ask what the customer has already tried.", "utterance_id": "u0002"},
        {"text": "Sum up what was done before closing.", "utterance_id": "u0004"},
    ],
}
PHASES: dict[str, Any] = {
    "phases": [
        {"phase": "greeting", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
        {"phase": "problem", "start_utterance_id": "u0001", "end_utterance_id": "u0001"},
        {"phase": "troubleshooting", "start_utterance_id": "u0002", "end_utterance_id": "u0002"},
        {"phase": "resolution", "start_utterance_id": "u0003", "end_utterance_id": "u0003"},
        {"phase": "close", "start_utterance_id": "u0004", "end_utterance_id": "u0004"},
    ]
}
METRICS = [{"key": "customer_talk_share", "value": 0.3, "unit": "ratio", "definition": "Customer share of speech."}]


@pytest.fixture
def call() -> PreparedTranscript:
    return prepare_transcript({
        "version": "transcript@v1", "timeline": "original", "asr_model": "fake-asr@1",
        "word_count": sum(len(t.split()) for *_, t in CALL_ROWS),
        "utterances": [
            {"role": r, "speaker_label": "S0" if r == "support_agent" else "S1", "start_ms": s, "end_ms": e,
             "text": t, "avg_confidence": 0.9, "low_confidence_spans": []}
            for r, s, e, t in CALL_ROWS
        ],
    })  # fmt: skip


@pytest.fixture
def rubric() -> Rubric:
    rubric, _ = load_rubric(Path(__file__).resolve().parents[3] / "rubrics" / "support.company.v0.1.yaml")
    return rubric


def test_a_support_call_report_has_a_verified_case_card(
    rubric: Rubric, call: PreparedTranscript, fake_judge: Any
) -> None:
    assert outcome_values(rubric.output_values) == OUTCOMES
    by_key = {d["key"]: d for d in SCORES["dimensions"]}
    scores = [{"dimensions": [by_key[d.key] for d in group]} for group in group_dimensions(rubric.dimensions)]
    moments = {"moments": [{"kind": "plus", "text": "Gave the complaint number and promised a follow-up call.",
                            "fact": None, "product_info_id": None, "quote": "kal tak ek follow up call bhi aayega",
                            "start_ms": 36_500, "utterance_id": "u0004"}]}  # fmt: skip
    model = fake_judge([*scores, SYNTHESIS, PHASES, CARD, moments])
    result = analyse(rubric=rubric, transcript=call, metrics=METRICS, model=model, analysed_roles={"support_agent"},
                     phase_names=DEFAULT_PHASES["support"], support=True)  # fmt: skip
    report = result.report
    jsonschema.validate(report, load_report_schema())
    assert result.next_status is RecordingStatus.COMPLETED
    card = report["case_card"]
    assert card["problem"]["evidence"] == {
        "quote": "login ke baad screen band ho jaati hai", "utterance_id": "u0001", "start_ms": 6_500, "end_ms": 15_000,
    }  # fmt: skip
    assert [s["by"] for s in card["steps_tried"]] == ["customer", "support_agent"]
    assert (card["outcome"]["value"], card["follow_up"]["due"], card["left_out"]) == ("solved", "tomorrow", 0)
    assert (
        "Allowed outcomes: solved, follow_up, escalated, not_solved, unclear"
        in (model.calls[-2]["messages"][0]["content"])
    )
    assert report["moments"]["items"][0]["evidence"]["utterance_id"] == "u0004"  # what was said well and badly


def test_an_item_whose_quote_is_not_in_the_transcript_is_reasked_then_left_out(
    call: PreparedTranscript, fake_judge: Any
) -> None:
    invented = {"step": "Updated the phone.", "by": "customer", "quote": "phone update kar diya", "start_ms": 6_500,
                "utterance_id": "u0001"}  # fmt: skip
    answer = {**CARD, "steps_tried": [*CARD["steps_tried"], invented]}
    model = fake_judge([answer, answer])
    outcome = write_case_card(call, outcomes=OUTCOMES, model=model)
    assert outcome.attempts == 2 and outcome.failure_reasons == ("quote_not_found",)
    assert outcome.card is not None and outcome.card.left_out == 1  # never shown, but counted
    assert [s.step for s in outcome.card.steps_tried] == ["Reinstalled the app.", "Cleared the app cache."]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"follow_up": {**CARD["follow_up"], "action": "Call [NAME_1] tomorrow."}}, "placeholder_in_text"),
        ({"follow_up": {**CARD["follow_up"], "owner": "manager"}}, "invalid_shape"),
        ({"steps_tried": [{**CARD["steps_tried"][0], "by": "technician"}]}, "invalid_shape"),
        ({"outcome": {"value": "fixed", "quote": None, "start_ms": None, "utterance_id": None}}, "invalid_shape"),
        ({"problem": {**CARD["problem"], "problem": "word " * 35}}, "too_long"),
    ],
)  # fmt: skip
def test_case_card_rules(call: PreparedTranscript, change: dict[str, Any], code: str) -> None:
    card, problems = validate_case_card({**CARD, **change}, transcript=call, outcomes=OUTCOMES)
    assert card is None and code in {p.code for p in problems}


def test_an_unclear_outcome_needs_no_quote_and_nothing_else_is_required(call: PreparedTranscript) -> None:
    answer: dict[str, Any] = {"product": None, "problem": None, "steps_tried": [], "follow_up": None,
              "outcome": {"value": "unclear", "quote": None, "start_ms": None, "utterance_id": None}}  # fmt: skip
    card, problems = validate_case_card(answer, transcript=call, outcomes=OUTCOMES)
    assert problems == [] and card is not None
    assert card.to_record() == {"product": None, "problem": None, "steps_tried": [], "follow_up": None,
                                "outcome": {"value": "unclear", "evidence": None}, "left_out": 0}  # fmt: skip
