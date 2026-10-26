"""Classify, phases and the reception ticket (P5.8), with the fake judge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.classify import UNCERTAIN_TYPE, classify, needs_classification
from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.phases import DEFAULT_PHASES, segment_phases
from sabha_analytics.reception import TICKET_FAILED, TicketValues, ticket_values, validate_ticket, write_ticket
from sabha_analytics.report import analyse, load_report_schema
from sabha_analytics.rubric import Rubric, load_rubric
from sabha_core.state import RecordingStatus

CALL_ROWS = (
    ("receptionist", 0, 6_000, "Namaste, Sunrise Public School, main Pooja bol rahi hoon."),
    ("caller", 6_500, 12_000, "Haan ji, mujhe Grade 3 admission ke baare mein poochna tha."),
    ("receptionist", 12_500, 20_000, "Toh aapko Grade 3 ka admission form chahiye, aur kuch?"),
    ("caller", 20_500, 24_000, "Bas fees kitni hai yeh bata dijiye."),
    ("receptionist", 24_500, 34_000, "Fees ki details accounts office kal shaam tak call karke batayega."),
    ("caller", 34_500, 36_000, "Theek hai, dhanyavaad."),
)
METRICS = [{"key": "caller_talk_share", "value": 0.4, "unit": "ratio", "definition": "Caller share of speech."}]

SCORES = {
    "dimensions": [
        {
            "key": "intent_captured",
            "score": 4,
            "rationale": "The receptionist confirms what the caller needs.",
            "evidence": [
                {"quote": "aapko Grade 3 ka admission form chahiye", "utterance_id": "u0002", "start_ms": 12_500}
            ],
        },
        {
            "key": "resolution",
            "score": 4,
            "rationale": "A next step and an owner are given.",
            "evidence": [
                {
                    "quote": "accounts office kal shaam tak call karke batayega",
                    "utterance_id": "u0004",
                    "start_ms": 24_500,
                }
            ],
        },
    ]
}
SYNTHESIS = {
    "summary": "A polite call that confirmed the need and gave a clear next step.",
    "strengths": ["Confirms what the caller needs.", "Names who will follow up."],
    "gaps": ["The fee question was not answered on the call.", "No time was confirmed with the caller."],
    "suggestions": [
        {"text": "Ask whether anything else is needed after confirming.", "utterance_id": "u0002"},
        {"text": "Give the fee range if it is published.", "utterance_id": "u0004"},
        {"text": "Agree a time for the callback.", "utterance_id": "u0004"},
    ],
}
PHASES = {
    "phases": [
        {"phase": "greeting", "start_utterance_id": "u0000", "end_utterance_id": "u0000"},
        {"phase": "need", "start_utterance_id": "u0001", "end_utterance_id": "u0002"},
        {"phase": "information", "start_utterance_id": "u0003", "end_utterance_id": "u0004"},
        {"phase": "close", "start_utterance_id": "u0005", "end_utterance_id": "u0005"},
    ]
}
TICKET = {
    "category": "admission_enquiry",
    "status": "follow_up_needed",
    "follow_up": {"text": "Call the caller back with the Grade 3 fees.", "owner_role": "accounts office"},
    "summary": "Caller asked about Grade 3 admission and fees; the accounts office will call back with the fees.",
    "need_quote": {"quote": "mujhe Grade 3 admission ke baare mein", "utterance_id": "u0001", "start_ms": 6_500},
    "outcome_quote": {"quote": "accounts office kal shaam tak call karke", "utterance_id": "u0004", "start_ms": 24_500},
}


def call_document() -> dict[str, Any]:
    return {
        "version": "transcript@v1",
        "timeline": "original",
        "asr_model": "fake-asr@1",
        "word_count": sum(len(t.split()) for *_, t in CALL_ROWS),
        "utterances": [
            {
                "role": r,
                "speaker_label": "S0" if r == "receptionist" else "S1",
                "start_ms": s,
                "end_ms": e,
                "text": t,
                "avg_confidence": 0.9,
                "low_confidence_spans": [],
            }
            for r, s, e, t in CALL_ROWS
        ],
    }


@pytest.fixture
def call() -> PreparedTranscript:
    return prepare_transcript(call_document())


@pytest.fixture
def reception_rubric() -> Rubric:
    rubric, _ = load_rubric(Path(__file__).parent / "fixtures" / "rubrics" / "reception.testing.v1.0.yaml")
    return rubric


# --- classify -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("set_type", "confidence", "expected"),
    [(None, None, True), ("teaching", None, False), ("teaching", 0.95, False), ("teaching", 0.4, True)],
)
def test_classification_is_needed_only_without_a_confident_type(
    set_type: str | None, confidence: float | None, expected: bool
) -> None:
    assert needs_classification(set_type, confidence) is expected


def test_a_confident_classification_is_kept(call: PreparedTranscript, fake_judge: Any) -> None:
    model = fake_judge([{"type": "reception", "language_mix": "hinglish", "confidence": 0.92}])
    result = classify(call, model=model, allowed_types=["teaching", "reception"])
    assert (result.type, result.language_mix, result.needs_review_reason) == ("reception", "hinglish", None)


def test_low_confidence_asks_for_review(call: PreparedTranscript, fake_judge: Any) -> None:
    model = fake_judge([{"type": "teaching", "language_mix": "hinglish", "confidence": 0.55}])
    assert classify(call, model=model, allowed_types=["teaching", "reception"]).needs_review_reason == UNCERTAIN_TYPE


def test_an_invalid_answer_is_reasked_once_then_gives_up(call: PreparedTranscript, fake_judge: Any) -> None:
    bad = {"type": "sales", "language_mix": "tamil", "confidence": 2}
    model = fake_judge([bad, bad])
    result = classify(call, model=model, allowed_types=["teaching", "reception"])
    assert len(model.calls) == 2 and result.type is None and result.needs_review_reason == UNCERTAIN_TYPE


def test_only_the_opening_three_minutes_are_sent(lesson: PreparedTranscript, fake_judge: Any) -> None:
    model = fake_judge([{"type": "teaching", "language_mix": "hinglish", "confidence": 0.9}])
    classify(lesson, model=model, allowed_types=["teaching"])
    prompt = model.calls[0]["messages"][0]["content"]
    assert "Chlorophyll leaf ka green pigment" in prompt  # at 34 s
    assert "kal experiment karenge" not in prompt  # at 500 s, after the first three minutes


def test_an_uncertain_type_is_not_scored(reception_rubric: Rubric, call: PreparedTranscript, fake_judge: Any) -> None:
    model = fake_judge([{"type": "teaching", "language_mix": "hinglish", "confidence": 0.5}])
    classification = classify(call, model=model, allowed_types=["teaching", "reception"])
    result = analyse(
        rubric=reception_rubric,
        transcript=call,
        metrics=METRICS,
        model=model,
        analysed_roles={"receptionist"},
        classification=classification,
    )
    assert result.next_status is RecordingStatus.NEEDS_REVIEW
    assert result.report["review_reasons"] == [UNCERTAIN_TYPE]
    assert result.report["dimensions"] == []
    assert len(model.calls) == 1  # only the classification call: nothing was scored
    jsonschema.validate(result.report, load_report_schema())


# --- phases ---------------------------------------------------------------------------------------------------------


def test_valid_phases_take_their_times_from_the_transcript(call: PreparedTranscript, fake_judge: Any) -> None:
    outcome = segment_phases(call, model=fake_judge([PHASES]), phase_names=DEFAULT_PHASES["reception"])
    assert outcome.phases is not None
    assert [(p.name, p.start_ms, p.end_ms) for p in outcome.phases] == [
        ("greeting", 0, 6_000),
        ("need", 6_500, 20_000),
        ("information", 20_500, 34_000),
        ("close", 34_500, 36_000),
    ]


@pytest.mark.parametrize(
    ("bad_phases", "code"),
    [
        ([{"phase": "greeting", "start_utterance_id": "u0000", "end_utterance_id": "u0099"}], "unknown_utterance"),
        ([{"phase": "need", "start_utterance_id": "u0002", "end_utterance_id": "u0001"}], "reversed"),
        (
            [
                {"phase": "need", "start_utterance_id": "u0001", "end_utterance_id": "u0003"},
                {"phase": "information", "start_utterance_id": "u0003", "end_utterance_id": "u0004"},
            ],
            "overlap",
        ),
        (
            [
                {"phase": "close", "start_utterance_id": "u0000", "end_utterance_id": "u0001"},
                {"phase": "greeting", "start_utterance_id": "u0002", "end_utterance_id": "u0003"},
            ],
            "phase_order",
        ),
        ([{"phase": "small talk", "start_utterance_id": "u0000", "end_utterance_id": "u0001"}], "unknown_phase"),
    ],
)
def test_bad_boundaries_are_reasked_then_dropped(
    call: PreparedTranscript, fake_judge: Any, bad_phases: list[dict[str, str]], code: str
) -> None:
    model = fake_judge([{"phases": bad_phases}, {"phases": bad_phases}])
    outcome = segment_phases(call, model=model, phase_names=DEFAULT_PHASES["reception"])
    assert outcome.phases is None and code in outcome.failure_reasons and len(model.calls) == 2


# --- reception ticket -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"category": "gossip"}, "invalid_category"),
        ({"status": "resolved"}, "unexpected_follow_up"),  # resolved calls have no follow-up
        ({"follow_up": None}, "missing_follow_up"),  # every call that is not resolved needs one
        ({"status": "escalated", "follow_up": None}, "missing_follow_up"),
        ({"status": "pending"}, "invalid_status"),  # the draft's word, not in the approved list
        ({"summary": "Caller [NAME_1] asked about fees."}, "placeholder_in_text"),
        ({"summary": "word " * 61}, "too_long"),
        (
            {"need_quote": {"quote": "main fees online bhar dunga", "utterance_id": "u0001", "start_ms": 6_500}},
            "quote_not_found",
        ),  # golden rule 5: a quote that is not in the transcript means no ticket
        ({"outcome_quote": None}, "invalid_shape"),
    ],
)
def test_ticket_rules(reception_rubric: Rubric, call: PreparedTranscript, change: dict[str, object],
                      code: str) -> None:  # fmt: skip
    values = ticket_values(reception_rubric.output_values)
    ticket, problems = validate_ticket({**TICKET, **change}, values, transcript=call)
    assert ticket is None and code in {p.code for p in problems}


def test_a_ticket_keeps_its_quotes_in_the_transcripts_own_words(reception_rubric: Rubric,
                                                                call: PreparedTranscript) -> None:  # fmt: skip
    loose = {**TICKET, "need_quote": {"quote": "Mujhe grade 3 admission ke baare me", "utterance_id": "u0001",
                                      "start_ms": 6_500}}  # fmt: skip
    ticket, problems = validate_ticket(loose, ticket_values(reception_rubric.output_values), transcript=call)
    assert problems == [] and ticket is not None
    record = ticket.to_record()["evidence"]
    assert record["need"] == {"quote": "mujhe Grade 3 admission ke baare mein", "utterance_id": "u0001",
                              "start_ms": 6_500, "end_ms": 12_000}  # fmt: skip
    assert record["outcome"]["utterance_id"] == "u0004" and record["outcome"]["end_ms"] == 34_000


def test_a_reception_call_yields_a_valid_ticket_style_report(
    reception_rubric: Rubric, call: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([SCORES, SYNTHESIS, PHASES, TICKET])
    result = analyse(
        rubric=reception_rubric,
        transcript=call,
        metrics=METRICS,
        model=model,
        analysed_roles={"receptionist"},
        phase_names=DEFAULT_PHASES["reception"],
        reception=True,
    )
    report = result.report
    jsonschema.validate(report, load_report_schema())
    assert result.next_status is RecordingStatus.COMPLETED
    assert report["ticket"]["category"] == "admission_enquiry"
    assert report["ticket"]["follow_up"] == {
        "text": "Call the caller back with the Grade 3 fees.",
        "owner_role": "accounts office",
    }
    assert report["ticket"]["evidence"]["outcome"]["quote"] == "accounts office kal shaam tak call karke"
    assert [p["phase"] for p in report["phases"]] == ["greeting", "need", "information", "close"]
    assert {"segment.system", "reception.system"} <= set(report["prompts"])


def test_a_failed_ticket_asks_for_review_but_keeps_the_scores(
    reception_rubric: Rubric, call: PreparedTranscript, fake_judge: Any
) -> None:
    bad = {**TICKET, "category": "gossip"}
    model = fake_judge([SCORES, SYNTHESIS, bad, bad])
    result = analyse(
        rubric=reception_rubric,
        transcript=call,
        metrics=METRICS,
        model=model,
        analysed_roles={"receptionist"},
        reception=True,
    )
    assert result.next_status is RecordingStatus.NEEDS_REVIEW
    assert result.report["review_reasons"] == [TICKET_FAILED]
    assert result.report["ticket"] is None
    assert all(d["verified"] for d in result.report["dimensions"])


def test_the_ticket_lists_come_from_the_rubric(reception_rubric: Rubric, call: PreparedTranscript,
                                              fake_judge: Any) -> None:  # fmt: skip
    values = ticket_values(reception_rubric.output_values)
    assert values == TicketValues(
        ("admission_enquiry", "fee_query", "transport", "general_information", "complaint", "other"),
        ("resolved", "follow_up_needed", "escalated"),
    )
    model = fake_judge([SCORES, SYNTHESIS, TICKET])
    analyse(rubric=reception_rubric, transcript=call, metrics=METRICS, model=model, analysed_roles={"receptionist"},
            reception=True)  # fmt: skip
    ticket_call = model.calls[-1]
    assert ticket_call["json_schema"]["properties"]["status"]["enum"] == list(values.statuses)
    assert "Allowed categories: admission_enquiry, fee_query, transport" in ticket_call["messages"][0]["content"]


def test_the_ticket_prompt_names_the_conversation_and_the_other_role(call: PreparedTranscript,
                                                                    fake_judge: Any) -> None:  # fmt: skip
    walk_in, _ = load_rubric(Path(__file__).resolve().parents[3] / "rubrics" / "reception.company.v0.1.yaml")
    values = ticket_values(walk_in.output_values)
    model = fake_judge([{**TICKET, "category": "appointment_or_meeting"}])
    outcome = write_ticket(call, values=values, model=model, rubric_id=walk_in.id, rubric_roles=walk_in.roles)
    assert outcome.ticket is not None and outcome.ticket.category == "appointment_or_meeting"
    system = model.calls[0]["system"]
    assert "front-desk conversation with a walk-in visitor" in system and 'say "the visitor"' in system
    assert "caller" not in system and "school" not in system

    school = fake_judge([TICKET])
    write_ticket(call, values=ticket_values(load_rubric(Path(__file__).resolve().parents[3] / "rubrics"
                                                        / "reception.school.v0.2.yaml")[0].output_values),
                 model=school, rubric_id="reception.school.v0.2", rubric_roles=("receptionist", "caller"))  # fmt: skip
    assert "a front-desk call" in school.calls[0]["system"] and 'say "the caller"' in school.calls[0]["system"]


def test_the_company_walk_in_rubric_has_its_own_ticket_categories() -> None:
    rubric, _ = load_rubric(Path(__file__).resolve().parents[3] / "rubrics" / "reception.company.v0.1.yaml")
    values = ticket_values(rubric.output_values)
    assert values.categories == ("appointment_or_meeting", "enquiry", "delivery_or_pickup", "payment_or_billing",
                                 "complaint", "interview_or_vendor", "other")  # fmt: skip
    assert values.statuses == ("resolved", "follow_up_needed", "escalated")
    assert tuple(rubric.roles) == ("receptionist", "visitor")


def test_the_approved_school_rubric_makes_tickets() -> None:
    rubric, _ = load_rubric(Path(__file__).resolve().parents[3] / "rubrics" / "reception.school.v0.2.yaml")
    assert ticket_values(rubric.output_values).statuses == ("resolved", "follow_up_needed", "escalated")


@pytest.mark.parametrize(
    ("output_values", "message"),
    [
        (None, "no output_values for category and status"),
        ({"category": ("other",)}, "no output_values for status"),
        ({"category": ("other",), "status": ("open", "closed")}, "must include 'resolved'"),
    ],
)
def test_a_rubric_that_cannot_make_tickets_is_refused(output_values: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ticket_values(output_values)


def test_a_reception_analysis_without_ticket_lists_fails_before_any_model_call(
    rubric: Rubric, call: PreparedTranscript, fake_judge: Any
) -> None:
    model = fake_judge([])
    with pytest.raises(ValueError, match="cannot make tickets"):
        analyse(rubric=rubric, transcript=call, metrics=METRICS, model=model, analysed_roles={"receptionist"},
                reception=True)  # fmt: skip
    assert model.calls == []
