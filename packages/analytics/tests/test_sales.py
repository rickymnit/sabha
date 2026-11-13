"""The deal card for an in-person sales meeting, with the fake judge: every item rests on a verified quote."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.moments import validate_moments, write_moments
from sabha_analytics.next_time import ProductFact, write_next_time
from sabha_analytics.phases import DEFAULT_PHASES
from sabha_analytics.report import analyse, load_report_schema
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_analytics.sales import interest_values, is_greeting, validate_deal_card, write_deal_card
from sabha_core.state import RecordingStatus

MEETING_ROWS = (
    ("sales_rep", 0, 7_000, "Namaste sir, main Rohit, Brightpath se. Pehle aapka process samajhna hai."),
    (
        "customer",
        7_500,
        18_000,
        "Sunrise School mein fees ka reconciliation Excel mein hota hai, har mahine do din lag jaate hain.",
    ),
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
    "current_setup": [
        {"fact": "Fee reconciliation is done in Excel.", "quote": "fees ka reconciliation Excel mein hota hai",
         "start_ms": 7_500, "utterance_id": "u0001"},
    ],
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
    "client_name": {"name": "Sunrise School", "quote": "Sunrise School mein fees", "start_ms": 7_500,
                    "utterance_id": "u0001"},
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
MOMENTS: dict[str, Any] = {"moments": [
    {"kind": "plus", "text": "Offered quarterly billing when the client said the price was high.", "fact": None,
     "product_info_id": None, "quote": "Quarterly billing ho sakti hai", "start_ms": 46_500, "utterance_id": "u0004"},
]}  # fmt: skip
METRICS = [{"key": "customer_talk_share", "value": 0.3, "unit": "ratio", "definition": "Customer share of speech."}]


def test_a_sales_meeting_report_has_a_verified_deal_card(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, CARD, MOMENTS])
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
    assert card["current_setup"][0]["fact"] == "Fee reconciliation is done in Excel."
    assert card["client_name"] == {"name": "Sunrise School", "evidence": {
        "quote": "Sunrise School mein fees", "utterance_id": "u0001", "start_ms": 7_500, "end_ms": 18_000}}  # fmt: skip
    assert "deal_card.system" in report["prompts"]
    assert "Allowed interest levels: high, medium, low, unclear" in model.calls[3]["messages"][0]["content"]
    assert report["moments"]["items"][0]["kind"] == "plus"  # what was said well and badly


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
    model = fake_judge([SCORES, SYNTHESIS, PHASES, bad, bad, MOMENTS])
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
        ({"current_setup": [CARD["current_setup"][0]] * 4}, "invalid_shape"),
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


# --- Coaching for the next conversation (sabha_analytics.next_time, founder's dashboard doc 2026-11-12) ---

COACHING: dict[str, Any] = {
    "question_to_ask": {"text": "Who else signs off on a new fee system?", "quote": "Pehle aapka process samajhna hai",
                        "start_ms": 0, "utterance_id": "u0000"},
    "explain_better": {"text": "Explain how quarterly billing works before the client asks about price.",
                       "quote": "Price thoda zyada lag raha hai", "start_ms": 40_500, "utterance_id": "u0003"},
    "practice_point": {"text": "Repeat the agreed next step and its time back to the client.",
                       "quote": "Thursday chaar baje call fix karte hain", "start_ms": 63_500, "utterance_id": "u0006"},
}  # fmt: skip


def test_a_sales_report_carries_verified_coaching_for_the_next_call(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, CARD, COACHING, MOMENTS])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, phase_names=DEFAULT_PHASES["sales"], sales=True,
                     next_time=True)  # fmt: skip
    report = result.report
    jsonschema.validate(report, load_report_schema())
    coaching = report["next_time"]
    assert coaching["practice_point"]["text"] == "Repeat the agreed next step and its time back to the client."
    assert coaching["practice_point"]["evidence"] == {
        "quote": "Thursday chaar baje call fix karte hain", "utterance_id": "u0006", "start_ms": 63_500,
        "end_ms": 72_000,
    }  # fmt: skip
    assert coaching["question_to_ask"]["text"].endswith("?") and coaching["left_out"] == 0
    assert "next_time.system" in report["prompts"]
    assert ": 4\n" in model.calls[4]["messages"][0]["content"]  # the verified scores steer the practice point


def test_a_tip_whose_quote_is_not_in_the_transcript_is_left_out(meeting: PreparedTranscript, fake_judge: Any) -> None:
    invented = {**COACHING, "explain_better": {**COACHING["explain_better"], "quote": "ERP integration kab tak hoga"}}
    model = fake_judge([invented, invented])
    outcome = write_next_time(meeting, dimensions=(), model=model)
    assert outcome.attempts == 2 and outcome.failure_reasons == ("quote_not_found",)
    assert outcome.next_time is not None and outcome.next_time.explain_better is None  # never shown
    assert outcome.next_time.practice_point is not None and outcome.next_time.left_out == 1


def test_without_the_flag_there_is_no_coaching_call(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, CARD, MOMENTS])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, phase_names=DEFAULT_PHASES["sales"], sales=True)  # fmt: skip
    assert result.report["next_time"] is None and len(model.calls) == 5  # scores, synthesis, phases, card, moments


def test_coaching_points_only_at_approved_product_information(meeting: PreparedTranscript, fake_judge: Any) -> None:
    facts = (ProductFact("pi-billing", "Quarterly billing", "Fees can be paid quarterly. Call 9876543210 for terms."),)
    with_entry = {**COACHING, "explain_better": {**COACHING["explain_better"], "product_info_id": "pi-billing"}}
    invented = {**COACHING, "explain_better": {**COACHING["explain_better"], "product_info_id": "pi-made-up"}}

    model = fake_judge([with_entry])
    outcome = write_next_time(meeting, dimensions=(), model=model, product_info=facts)
    assert outcome.next_time is not None and outcome.next_time.explain_better is not None
    assert outcome.next_time.to_record()["explain_better"]["product_info_id"] == "pi-billing"
    prompt = model.calls[0]["messages"][0]["content"]
    assert "[pi-billing] Quarterly billing: Fees can be paid quarterly." in prompt
    assert "9876543210" not in prompt  # company text is masked for PII too (golden rule 8)

    model = fake_judge([invented, invented])
    outcome = write_next_time(meeting, dimensions=(), model=model, product_info=facts)
    assert outcome.next_time is None and outcome.failure_reasons == ("unknown_product_info",)  # never shown


def test_coaching_in_another_script_is_sent_back_for_english(meeting: PreparedTranscript, fake_judge: Any) -> None:
    hindi = {**COACHING, "practice_point": {**COACHING["practice_point"], "text": "शुरू में अपना परिचय दें"}}
    model = fake_judge([hindi, COACHING])
    outcome = write_next_time(meeting, dimensions=(), model=model, product_info=())
    assert outcome.next_time is not None and outcome.attempts == 2
    assert "write the text in English" in str(model.calls[1]["messages"])


@pytest.mark.parametrize(("name", "greeting"), [("खम्मा गनी", True), ("Khamma Ghani!", True), ("नमस्ते।", True),
                                                ("Edge Retail Solutions", False), ("इंद्रधनुष 8", False)])  # fmt: skip
def test_a_greeting_is_never_taken_for_the_client_name(name: str, greeting: bool) -> None:
    assert is_greeting(name) is greeting


# --- What was said well and badly (sabha_analytics.moments, owner 2026-11-13) ---

KB_FACTS = (ProductFact("pi-billing", "Billing terms", "Software is billed yearly in advance. Helpline 9876543210."),)
WRONG = {"kind": "drawback", "text": "Promised quarterly billing; the approved terms say yearly in advance.",
         "fact": "contradicts", "product_info_id": "pi-billing", "quote": "Quarterly billing ho sakti hai",
         "start_ms": 46_500, "utterance_id": "u0004"}  # fmt: skip
PLUS = {"kind": "plus", "text": "Fixed a call for Thursday at four.", "fact": None, "product_info_id": None,
        "quote": "Thursday chaar baje call fix karte hain", "start_ms": 63_500, "utterance_id": "u0006"}  # fmt: skip


def test_a_contradicted_fact_is_a_drawback_naming_its_entry(meeting: PreparedTranscript, fake_judge: Any) -> None:
    model = fake_judge([{"moments": [PLUS, WRONG]}])
    outcome = write_moments(
        meeting, staff_role="sales rep", conversation="sales call", model=model, product_info=KB_FACTS
    )
    assert outcome.moments is not None
    items = outcome.moments.to_record()["items"]
    assert [i["kind"] for i in items] == ["drawback", "plus"]  # in the order they were said
    assert items[0]["fact"] == "contradicts" and items[0]["product_info_id"] == "pi-billing"
    assert items[0]["evidence"] == {"quote": "Quarterly billing ho sakti hai", "utterance_id": "u0004",
                                    "start_ms": 46_500, "end_ms": 58_000}  # fmt: skip
    prompt = model.calls[0]["messages"][0]["content"]
    assert "[pi-billing] Billing terms: Software is billed yearly" in prompt and "9876543210" not in prompt


@pytest.mark.parametrize(("change", "code"), [
    ({"product_info_id": "pi-made-up"}, "unknown_product_info"),
    ({"product_info_id": None}, "fact_without_entry"),
    ({"fact": "not_covered"}, "entry_without_fact"),
    ({"kind": "plus"}, "contradiction_as_plus"),
    ({"text": "बिलिंग गलत बताई"}, "not_english"),
])  # fmt: skip
def test_a_product_verdict_must_fit_an_approved_entry(meeting: PreparedTranscript, change: dict[str, Any],
                                                      code: str) -> None:  # fmt: skip
    found, problems = validate_moments({"moments": [{**WRONG, **change}]}, transcript=meeting,
                                       product_ids=frozenset({"pi-billing"}))  # fmt: skip
    assert found is None and [p.code for p in problems] == [code]


def test_a_moment_whose_quote_is_not_said_is_left_out(meeting: PreparedTranscript, fake_judge: Any) -> None:
    invented = {**PLUS, "quote": "hum free installation denge"}
    model = fake_judge([{"moments": [PLUS, invented]}] * 2)
    outcome = write_moments(meeting, staff_role="sales rep", conversation="sales call", model=model)
    assert outcome.attempts == 2 and outcome.failure_reasons == ("quote_not_found",)
    assert outcome.moments is not None and len(outcome.moments.items) == 1 and outcome.moments.left_out == 1


def test_sales_scoring_judges_product_statements_against_the_knowledge_base(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, CARD, {"moments": [WRONG]}])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, sales=True, phase_names=None, product_info=KB_FACTS)  # fmt: skip
    scoring_prompt = model.calls[0]["messages"][0]["content"]
    assert "# Approved product information" in scoring_prompt and "[pi-billing] Billing terms" in scoring_prompt
    assert result.report["moments"]["items"][0]["fact"] == "contradicts"


def test_other_types_keep_the_scoring_prompt_without_product_information(
    sales_rubric: Rubric, meeting: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS])
    result = analyse(rubric=sales_rubric, transcript=meeting, metrics=METRICS, model=model,
                     analysed_roles={"sales_rep"}, product_info=KB_FACTS)  # fmt: skip
    assert "Approved product information" not in model.calls[0]["messages"][0]["content"]
    assert result.report["moments"] is None
