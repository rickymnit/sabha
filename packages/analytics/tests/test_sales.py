"""The deal card for an in-person sales meeting, with the fake judge: every item rests on a verified quote."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.phases import DEFAULT_PHASES
from sabha_analytics.report import analyse, load_report_schema
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_analytics.sales import interest_values, validate_deal_card, write_deal_card
from sabha_core.state import RecordingStatus

MEETING_ROWS = (
    ("sales_rep", 0, 7_000, "Namaste sir, main Rohit, Brightpath se. Pehle aapka process samajhna hai."),
    ("customer", 7_500, 18_000, "Abhi fees ka reconciliation Excel mein hota hai, har mahine do din lag jaate hain."),
    (
        "sales_rep",
        18_500,
        40_000,
        "Yeh auto-match screen bank statement se direct match karti hai, do din bach jayenge.",
    ),
    ("customer", 40_500, 46_000, "Price thoda zyada lag raha hai is quarter ke budget ke liye."),
    (
        "sales_rep",
        46_500,
        58_000,
        "Quarterly billing ho sakti hai, pehla instalment April mein, kya isse kaam chalega?",
    ),
    ("customer", 58_500, 63_000, "Haan quarterly billing se chal jayega, quotation bhej dijiye."),
    ("sales_rep", 63_500, 72_000, "Main kal tak quotation bhejta hoon, aur Thursday chaar baje call fix karte hain."),
)


def meeting_document() -> dict[str, Any]:
    return {
        "version": "transcript@v1",
        "timeline": "original",
        "asr_model": "fake-asr@1",
        "word_count": sum(len(t.split()) for *_, t in MEETING_ROWS),
        "utterances": [
            {"role": r, "speaker_label": "S0" if r == "sales_rep" else "S1", "start_ms": s, "end_ms": e, "text": t,
             "avg_confidence": 0.9, "low_confidence_spans": []}
            for r, s, e, t in MEETING_ROWS
        ],
    }  # fmt: skip


@pytest.fixture
def meeting() -> PreparedTranscript:
    return prepare_transcript(meeting_document())


@pytest.fixture
def sales_rubric() -> Rubric:
    rubric, _ = load_rubric(Path(__file__).parent / "fixtures" / "rubrics" / "sales.testing.v1.0.yaml")
    return rubric


INTEREST = ("high", "medium", "low", "unclear")
CARD: dict[str, Any] = {
    "customer_needs": [
        {"need": "Cut the two days spent on fee reconciliation each month.",
         "quote": "har mahine do din lag jaate hain", "start_ms": 7_500, "utterance_id": "u0001"},
    ],
    "objections": [
        {"objection": "The price is high for this quarter's budget.",
         "response": "The rep offered quarterly billing with the first instalment in April.", "settled": "yes",
         "quote": "Price thoda zyada lag raha hai", "start_ms": 40_500, "utterance_id": "u0003"},
    ],
    "interest_level": {"value": "high", "quote": "quotation bhej dijiye", "start_ms": 58_500, "utterance_id": "u0005"},
    "next_step": {"action": "Send the quotation and hold a call on Thursday.", "owner": "both",
                  "due": "Thursday 4 pm", "quote": "Main kal tak quotation bhejta hoon", "start_ms": 63_500,
                  "utterance_id": "u0006"},
}  # fmt: skip
SCORES: dict[str, Any] = {
    "dimensions": [
        {"key": "discovery", "score": 4, "rationale": "The rep asks about the current process.",
         "evidence": [{"quote": "Pehle aapka process samajhna hai", "utterance_id": "u0000", "start_ms": 0}]},
        {"key": "next_step_commitment", "score": 4, "rationale": "An action and a day are agreed.",
         "evidence": [{"quote": "Thursday chaar baje call fix karte hain", "utterance_id": "u0006",
                       "start_ms": 63_500}]},
    ]
}  # fmt: skip
SYNTHESIS: dict[str, Any] = {
    "summary": "A focused meeting that found the reconciliation problem and agreed a next step.",
    "strengths": ["Asks about the current process.", "Answers the price concern with an option."],
    "gaps": ["Few questions about who decides.", "The rep did most of the talking."],
    "suggestions": [
        {"text": "Ask who else signs off before the demo.", "utterance_id": "u0000"},
        {"text": "Check the fit right after asking about the process.", "utterance_id": "u0000"},
        {"text": "Repeat the agreed next step back.", "utterance_id": "u0006"},
    ],
}
PHASES: dict[str, Any] = {
    "phases": [
        {"phase": "opening", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
        {"phase": "discovery", "start_utterance_id": "u0001", "end_utterance_id": "u0001"},
        {"phase": "presentation", "start_utterance_id": "u0002", "end_utterance_id": "u0002"},
        {"phase": "objections", "start_utterance_id": "u0003", "end_utterance_id": "u0005"},
        {"phase": "close", "start_utterance_id": "u0006", "end_utterance_id": "u0006"},
    ]
}
METRICS = [{"key": "customer_talk_share", "value": 0.3, "unit": "ratio", "definition": "Customer share of speech."}]


def test_a_sales_meeting_report_has_a_verified_deal_card(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, CARD])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, phase_names=DEFAULT_PHASES["sales"], sales=True)  # fmt: skip
    report = result.report
    jsonschema.validate(report, load_report_schema())
    assert result.next_status is RecordingStatus.COMPLETED
    card = report["deal_card"]
    assert card["customer_needs"][0]["evidence"] == {
        "quote": "har mahine do din lag jaate hain", "utterance_id": "u0001", "start_ms": 7_500, "end_ms": 18_000,
    }  # fmt: skip
    assert (card["objections"][0]["settled"], card["interest_level"]["value"]) == ("yes", "high")
    assert card["next_step"]["due"] == "Thursday 4 pm" and card["left_out"] == 0
    assert "deal_card.system" in report["prompts"]
    assert "Allowed interest levels: high, medium, low, unclear" in model.calls[-1]["messages"][0]["content"]


def test_an_item_whose_quote_is_not_in_the_transcript_is_reasked_then_left_out(
    meeting: PreparedTranscript, fake_judge: Any
) -> None:
    invented = {"need": "Integration with their ERP.", "quote": "humein ERP integration chahiye", "start_ms": 7_500,
                "utterance_id": "u0001"}  # fmt: skip
    answer = {**CARD, "customer_needs": [*CARD["customer_needs"], invented]}
    model = fake_judge([answer, answer])
    outcome = write_deal_card(meeting, interest=INTEREST, model=model)
    assert outcome.attempts == 2 and outcome.failure_reasons == ("quote_not_found",)
    assert "was not found in the transcript" in model.calls[1]["messages"][-1]["content"]  # told why, once
    assert outcome.card is not None
    assert [n.need for n in outcome.card.customer_needs] == ["Cut the two days spent on fee reconciliation each month."]
    assert outcome.card.left_out == 1  # never shown, but counted


def test_an_invalid_answer_twice_gives_no_card_but_the_scores_stand(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    bad = {**CARD, "next_step": {**CARD["next_step"], "owner": "intern"}}
    model = fake_judge([SCORES, SYNTHESIS, PHASES, bad, bad])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, phase_names=DEFAULT_PHASES["sales"], sales=True)  # fmt: skip
    assert result.report["deal_card"] is None
    assert result.next_status is RecordingStatus.COMPLETED  # no card is not a reason to stop the recording
    assert result.report["overall"]["score"] is not None


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"next_step": {**CARD["next_step"], "action": "Call [NAME_1] on Thursday."}}, "placeholder_in_text"),
        ({"objections": [{**CARD["objections"][0], "settled": "maybe"}]}, "invalid_shape"),
        ({"interest_level": {"value": "ecstatic", "quote": None, "start_ms": None, "utterance_id": None}},
         "invalid_shape"),
        ({"customer_needs": [{**CARD["customer_needs"][0], "need": "word " * 25}]}, "too_long"),
    ],
)  # fmt: skip
def test_deal_card_rules(meeting: PreparedTranscript, change: dict[str, Any], code: str) -> None:
    card, problems = validate_deal_card({**CARD, **change}, transcript=meeting, interest=INTEREST)
    assert card is None and code in {p.code for p in problems}


def test_unclear_interest_needs_no_quote_and_no_next_step_is_allowed(meeting: PreparedTranscript) -> None:
    answer = {**CARD, "interest_level": {"value": "unclear", "quote": None, "start_ms": None, "utterance_id": None},
              "next_step": None, "objections": []}  # fmt: skip
    card, problems = validate_deal_card(answer, transcript=meeting, interest=INTEREST)
    assert problems == [] and card is not None
    assert card.to_record()["interest_level"] == {"value": "unclear", "evidence": None}
    assert card.next_step is None and card.objections == ()


def test_the_interest_levels_come_from_the_rubric() -> None:
    rubric, _ = load_rubric(Path(__file__).resolve().parents[3] / "rubrics" / "sales.company.v0.1.yaml")
    assert interest_values(rubric.output_values) == ("high", "medium", "low", "unclear")
    with pytest.raises(ValueError, match="cannot make deal cards"):
        interest_values({"category": ["x"]})
    with pytest.raises(ValueError, match="must include 'unclear'"):
        interest_values({"interest_level": ["high", "low"]})
