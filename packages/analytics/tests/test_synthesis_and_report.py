"""Overall score, synthesis and the final report (P5.7), end to end with a fake model."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.report import InvalidReport, analyse, check_report, load_report_schema
from sabha_analytics.rubric import Rubric
from sabha_analytics.scoring import DimensionResult
from sabha_analytics.synthesis import LOW_VERIFICATION, SYNTHESIS_FAILED, compute_overall
from sabha_core.state import RecordingStatus

METRICS = [{"key": "teacher_talk_share", "value": 0.82, "unit": "share", "definition": "Teacher speech time share."}]


def dim(key: str, weight: float, score: int | None, verified: bool = True) -> DimensionResult:
    return DimensionResult(key, key, weight, verified, score if verified else None, "r" if verified else None, (), 1)


def not_applicable(key: str, weight: float) -> DimensionResult:
    return DimensionResult(key, key, weight, True, None, "r", (), 1, not_applicable=True)


# --- overall score ---------------------------------------------------------------------------------------------------


def test_overall_is_the_weighted_mean_of_verified_dimensions() -> None:
    assert compute_overall([dim("a", 0.6, 4), dim("b", 0.4, 3)]).score == 3.6


def test_overall_rounds_half_up() -> None:
    # 0.25 * 4 + 0.75 * 3 = 3.25 exactly; Python's round() would give 3.2.
    assert compute_overall([dim("a", 0.25, 4), dim("b", 0.75, 3)]).score == 3.3


def test_unverified_dimensions_are_left_out_of_the_mean() -> None:
    overall = compute_overall([dim("a", 0.6, 4), dim("b", 0.4, None, verified=False)])
    assert overall.score == 4.0  # 60% of the weight is verified: just enough
    assert overall.verified_share == 0.6


def test_no_overall_below_sixty_percent_verified_weight() -> None:
    overall = compute_overall([dim("a", 0.5, 5), dim("b", 0.5, None, verified=False)])
    assert overall.score is None and overall.needs_review


def test_a_not_applicable_dimension_leaves_the_total_and_the_rest_is_rescaled() -> None:
    overall = compute_overall([dim("a", 0.5, 4), dim("b", 0.3, 2), not_applicable("c", 0.2)])
    assert overall.score == 3.3  # (0.5 * 4 + 0.3 * 2) / 0.8 = 3.25, half up
    assert (overall.total_weight, overall.verified_share) == (0.8, 1.0)


def test_unverified_dimensions_stay_in_the_total_when_another_is_not_applicable() -> None:
    # 0.4 verified of 0.8 applicable is 50%: no score, although 0.4 + 0.2 of the rubric was answered.
    overall = compute_overall([dim("a", 0.4, 4), dim("b", 0.4, None, verified=False), not_applicable("c", 0.2)])
    assert overall.score is None and overall.verified_share == 0.5


def test_nothing_applicable_gives_no_overall_score() -> None:
    assert compute_overall([not_applicable("a", 1.0)]).score is None


# --- synthesis and report --------------------------------------------------------------------------------------------


def good_synthesis(**change: Any) -> dict[str, Any]:
    base = {
        "summary": "A clear lesson on photosynthesis with a short recap at the end.",
        "strengths": ["Defines key terms in plain words.", "Links ideas to everyday experience."],
        "gaps": ["Few checks that students understood.", "The recap is brief."],
        "suggestions": [
            {"text": "Ask a student to explain photosynthesis back in their own words.", "utterance_id": "u0001"},
            {"text": "Pause after defining chlorophyll and ask why leaves are green.", "utterance_id": "u0003"},
            {"text": "Let students state the two key ideas in the recap.", "utterance_id": "u0004"},
        ],
    }
    return {**base, **change}


def scoring_answer(answers: Any) -> dict[str, Any]:
    return {"dimensions": [answers.good_concept, answers.good_recap]}


def run(rubric: Rubric, lesson: PreparedTranscript, model: Any) -> Any:
    return analyse(rubric=rubric, transcript=lesson, metrics=METRICS, model=model, analysed_roles={"teacher"})


def test_a_complete_analysis_is_valid_and_completed(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                    answers: Any) -> None:  # fmt: skip
    result = run(rubric, lesson, fake_judge([scoring_answer(answers), good_synthesis()]))
    report = result.report

    jsonschema.validate(report, load_report_schema())
    assert result.next_status is RecordingStatus.COMPLETED
    assert report["overall"]["score"] == 3.6  # 0.6 * 4 + 0.4 * 3
    assert [s["start_ms"] for s in report["synthesis"]["suggestions"]] == [9_000, 34_000, 500_000]
    assert report["prompts"]["scoring.system"]["sha256"]
    assert report["model_ids"] == ["fake-judge@1"]
    assert report["usage"]["total"]["input_tokens"] == 200  # two calls of 100


def test_a_planted_fake_quote_never_reaches_the_report(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                       answers: Any) -> None:  # fmt: skip
    # The fake quote is offered twice for concept_clarity, so that dimension is excluded.
    model = fake_judge(
        [{"dimensions": [answers.bad_concept, answers.good_recap]}, {"dimensions": [answers.bad_concept]}]
    )
    result = run(rubric, lesson, model)
    text = json.dumps(result.report, ensure_ascii=False)

    assert answers.fake_quote not in text
    concept = next(d for d in result.report["dimensions"] if d["key"] == "concept_clarity")
    assert concept == {**concept, "verified": False, "score": None, "rationale": None, "evidence": []}
    # 0.4 of the weight verified is below 60%: no overall score, no synthesis call, review requested.
    assert result.report["overall"]["score"] is None
    assert result.next_status is RecordingStatus.NEEDS_REVIEW
    assert result.report["review_reasons"] == [LOW_VERIFICATION]
    assert len(model.calls) == 2
    jsonschema.validate(result.report, load_report_schema())


def test_evidence_is_the_transcripts_wording_not_the_models(rubric: Rubric, lesson: PreparedTranscript,
                                                           fake_judge: Any, answers: Any) -> None:  # fmt: skip
    sloppy = answers.good_concept
    sloppy["evidence"][1]["quote"] = "chlorophyl leaf ka green pigmant hai"  # small ASR-style misspellings
    result = run(rubric, lesson, fake_judge([{"dimensions": [sloppy, answers.good_recap]}, good_synthesis()]))
    quotes = [e["quote"] for d in result.report["dimensions"] for e in d["evidence"]]
    assert "chlorophyl leaf ka green pigmant hai" not in quotes
    assert any(q.startswith("Chlorophyll leaf ka green pigment hai") for q in quotes)


def test_no_pii_in_the_report(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any) -> None:
    result = run(rubric, lesson, fake_judge([scoring_answer(answers), good_synthesis()]))
    text = json.dumps(result.report, ensure_ascii=False)
    assert "9876543210" not in text and "Aman" not in text


def test_a_suggestion_on_a_student_line_is_reasked(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                   answers: Any) -> None:  # fmt: skip
    student_line = {"text": "Follow up on this question.", "utterance_id": "u0002"}
    on_student = good_synthesis(suggestions=[*good_synthesis()["suggestions"][:2], student_line])
    model = fake_judge([scoring_answer(answers), on_student, good_synthesis()])
    result = run(rubric, lesson, model)
    assert "u0002 which the staff member did not say" in model.calls[2]["messages"][0]["content"].replace(",", "")
    assert result.next_status is RecordingStatus.COMPLETED


def test_synthesis_failing_twice_asks_for_review_and_keeps_scores(
    rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any
) -> None:
    named = good_synthesis(summary="Good lesson, though [STUDENT_1] was distracted.")
    result = run(rubric, lesson, fake_judge([scoring_answer(answers), named, named]))
    assert result.report["synthesis"] is None
    assert result.report["review_reasons"] == [SYNTHESIS_FAILED]
    assert result.next_status is RecordingStatus.NEEDS_REVIEW
    assert all(d["verified"] for d in result.report["dimensions"])


def test_check_report_refuses_a_tampered_report(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                answers: Any) -> None:  # fmt: skip
    report = run(rubric, lesson, fake_judge([scoring_answer(answers), good_synthesis()])).report
    report["dimensions"][0]["evidence"][0]["quote"] = answers.fake_quote
    with pytest.raises(InvalidReport, match="not the transcript's own wording"):
        check_report(report, lesson)


def concept_only_synthesis() -> dict[str, Any]:
    """Suggestions only on lines the verified, applicable dimension cited (u0001, u0003)."""
    suggestions = [{**s, "utterance_id": "u0001"} if s["utterance_id"] == "u0004" else s
                   for s in good_synthesis()["suggestions"]]  # fmt: skip
    return good_synthesis(suggestions=suggestions)


def test_a_not_applicable_dimension_in_the_report(optional_recap_rubric: Rubric, lesson: PreparedTranscript,
                                                  fake_judge: Any, answers: Any) -> None:  # fmt: skip
    scoring = {"dimensions": [answers.good_concept, answers.recap_not_applicable]}
    result = run(optional_recap_rubric, lesson, fake_judge([scoring, concept_only_synthesis()]))
    report = result.report

    jsonschema.validate(report, load_report_schema())
    recap = next(d for d in report["dimensions"] if d["key"] == "recap_and_closure")
    assert recap["not_applicable"] is True and recap["verified"] is True and recap["score"] is None
    assert recap["rationale"] and recap["evidence"]
    assert "not_applicable" not in next(d for d in report["dimensions"] if d["key"] == "concept_clarity")
    assert report["overall"]["score"] == 4.0  # concept alone, rescaled to the whole
    assert result.next_status is RecordingStatus.COMPLETED


@pytest.mark.parametrize("tamper", [{"score": 3}, {"evidence": []}, {"rationale": None}])
def test_check_report_refuses_a_malformed_not_applicable_dimension(
    optional_recap_rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any, tamper: dict[str, Any]
) -> None:
    scoring = {"dimensions": [answers.good_concept, answers.recap_not_applicable]}
    report = run(optional_recap_rubric, lesson, fake_judge([scoring, concept_only_synthesis()])).report
    recap = next(d for d in report["dimensions"] if d["key"] == "recap_and_closure")
    recap.update(tamper)
    with pytest.raises(InvalidReport, match="not-applicable dimension needs no score"):
        check_report(report, lesson)


def test_a_suggestion_naming_an_utterance_id_is_reasked(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                        answers: Any) -> None:  # fmt: skip
    # Found in the first real run: "At utterance u0000, try pausing longer..." People read this text.
    with_id = good_synthesis(suggestions=[{"text": "At utterance u0001, ask a student to explain it back.",
                                           "utterance_id": "u0001"}, *good_synthesis()["suggestions"][1:]])  # fmt: skip
    model = fake_judge([scoring_answer(answers), with_id, good_synthesis()])
    result = run(rubric, lesson, model)
    assert "mentions u0001" in model.calls[2]["messages"][0]["content"]
    assert "u0001," not in json.dumps(result.report["synthesis"])
