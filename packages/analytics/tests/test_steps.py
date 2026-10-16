"""Classify, phases and the reception ticket (P5.8), with the fake judge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sabha_analytics.classify import UNCERTAIN_TYPE, classify, needs_classification
from sabha_analytics.grounding import PreparedTranscript, prepare_transcript
from sabha_analytics.phases import DEFAULT_PHASES, segment_phases
from sabha_analytics.reception import TICKET_FAILED, validate_ticket
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
    "category": "admission",
    "status": "pending",
    "follow_up": {"text": "Call the caller back with the Grade 3 fees.", "owner_role": "accounts office"},
    "summary": "Caller asked about Grade 3 admission and fees; the accounts office will call back with the fees.",
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
        ({"follow_up": None}, "missing_follow_up"),  # pending calls need one
        ({"summary": "Caller [NAME_1] asked about fees."}, "placeholder_in_text"),
        ({"summary": "word " * 61}, "too_long"),
    ],
)
def test_ticket_rules(change: dict[str, object], code: str) -> None:
    ticket, problems = validate_ticket({**TICKET, **change})
    assert ticket is None and code in {p.code for p in problems}


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
    assert report["ticket"]["category"] == "admission"
    assert report["ticket"]["follow_up"] == {
        "text": "Call the caller back with the Grade 3 fees.",
        "owner_role": "accounts office",
    }
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
