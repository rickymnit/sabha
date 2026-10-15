"""Scoring with grounded evidence (P5.6): verification, one re-ask per failing dimension, exclusion, redaction."""

from __future__ import annotations

from typing import Any

import pytest

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.rubric import Rubric
from sabha_analytics.scoring import (
    TASK_SCORING,
    PromptNotRedacted,
    check_prompt_redacted,
    group_dimensions,
    score_dimensions,
)

METRICS = [{"key": "teacher_talk_share", "value": 0.82, "unit": "share", "definition": "Teacher speech time share."}]


def run(rubric: Rubric, lesson: PreparedTranscript, model: Any) -> Any:
    return score_dimensions(rubric=rubric, transcript=lesson, metrics=METRICS, model=model)


def by_key(outcome: Any) -> dict[str, Any]:
    return {d.key: d for d in outcome.dimensions}


def test_good_answer_is_verified_in_one_call(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                             answers: Any) -> None:  # fmt: skip
    model = fake_judge([{"dimensions": [answers.good_concept, answers.good_recap]}])
    outcome = run(rubric, lesson, model)
    results = by_key(outcome)

    assert len(model.calls) == 1  # 2 dimensions fit in one call
    assert model.calls[0]["task"] == TASK_SCORING
    assert all(d.verified and d.attempts == 1 for d in outcome.dimensions)
    assert results["concept_clarity"].score == 4
    # Times come from the transcript, not from the model's claim.
    assert [(e.utterance_id, e.start_ms, e.end_ms) for e in results["concept_clarity"].evidence] == [
        ("u0001", 9_000, 30_000),
        ("u0003", 34_000, 40_000),
    ]


def test_one_fake_quote_triggers_one_reask_of_that_dimension_only(
    rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any
) -> None:
    model = fake_judge(
        [{"dimensions": [answers.bad_concept, answers.good_recap]}, {"dimensions": [answers.good_concept]}]
    )
    outcome = run(rubric, lesson, model)
    results = by_key(outcome)

    assert len(model.calls) == 2
    reask = model.calls[1]
    assert reask["json_schema"]["properties"]["dimensions"]["items"]["properties"]["key"]["enum"] == ["concept_clarity"]
    assert "was not found in any single transcript line" in reask["messages"][0]["content"]
    assert results["concept_clarity"].verified and results["concept_clarity"].attempts == 2
    assert results["recap_and_closure"].verified and results["recap_and_closure"].attempts == 1


def test_a_dimension_that_fails_twice_is_excluded_with_nothing_kept(
    rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any
) -> None:
    model = fake_judge(
        [{"dimensions": [answers.bad_concept, answers.good_recap]}, {"dimensions": [answers.bad_concept]}]
    )
    outcome = run(rubric, lesson, model)
    concept = by_key(outcome)["concept_clarity"]

    assert len(model.calls) == 2  # never a third try
    assert not concept.verified
    assert concept.score is None and concept.rationale is None and concept.evidence == ()
    assert "quote_not_found" in concept.failure_reasons
    assert by_key(outcome)["recap_and_closure"].verified


def test_invalid_json_is_reasked_per_dimension(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                               answers: Any) -> None:  # fmt: skip
    model = fake_judge([None, {"dimensions": [answers.good_concept]}, {"dimensions": [answers.good_recap]}])
    outcome = run(rubric, lesson, model)

    assert len(model.calls) == 3
    assert all(d.verified and d.attempts == 2 for d in outcome.dimensions)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"score": 6}, "invalid_score"),
        ({"score": "4"}, "invalid_score"),
        ({"rationale": "word " * 61}, "too_long"),
        ({"rationale": "Good, though [STUDENT_1] asked twice."}, "placeholder_in_text"),
    ],
)
def test_invalid_answers_never_survive_two_attempts(
    rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any, change: dict[str, object], code: str
) -> None:
    bad = {**answers.good_concept, **change}
    model = fake_judge([{"dimensions": [bad, answers.good_recap]}, {"dimensions": [bad]}])
    concept = by_key(run(rubric, lesson, model))["concept_clarity"]
    assert not concept.verified
    assert code in concept.failure_reasons


def test_the_same_passage_twice_does_not_meet_two_quotes(
    rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any, answers: Any
) -> None:
    good = answers.good_concept
    twice = {**good, "evidence": [good["evidence"][0], good["evidence"][0]]}
    model = fake_judge([{"dimensions": [twice, answers.good_recap]}, {"dimensions": [twice]}])
    concept = by_key(run(rubric, lesson, model))["concept_clarity"]
    assert not concept.verified
    assert "too_few_quotes" in concept.failure_reasons


def test_prompts_carry_redacted_text_only(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                          answers: Any) -> None:  # fmt: skip
    model = fake_judge([{"dimensions": [answers.good_concept, answers.good_recap]}])
    run(rubric, lesson, model)
    text = "\n".join(model.prompt_texts())

    assert "9876543210" not in text and "Aman" not in text
    assert "[PHONE_1]" in text and "[STUDENT_1]" in text


def test_metrics_are_given_as_context(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                      answers: Any) -> None:  # fmt: skip
    model = fake_judge([{"dimensions": [answers.good_concept, answers.good_recap]}])
    run(rubric, lesson, model)
    assert "teacher_talk_share = 0.82" in model.calls[0]["messages"][0]["content"]


def test_prompt_versions_and_hashes_are_recorded(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                 answers: Any) -> None:  # fmt: skip
    outcome = run(rubric, lesson, fake_judge([{"dimensions": [answers.good_concept, answers.good_recap]}]))
    assert {p.name for p in outcome.prompts} == {"scoring.system", "scoring.context", "scoring.request"}
    assert all(len(p.sha256) == 64 and p.version for p in outcome.prompts)


def test_cache_prefix_is_the_start_of_the_message(rubric: Rubric, lesson: PreparedTranscript, fake_judge: Any,
                                                  answers: Any) -> None:  # fmt: skip
    model = fake_judge(
        [{"dimensions": [answers.bad_concept, answers.good_recap]}, {"dimensions": [answers.good_concept]}]
    )
    run(rubric, lesson, model)
    prefixes = {call["cache_prefix"] for call in model.calls}
    assert len(prefixes) == 1  # the re-ask reuses the cached prefix
    assert all(call["messages"][0]["content"].startswith(call["cache_prefix"]) for call in model.calls)


def test_pii_guard_refuses_a_prompt_with_a_phone_number() -> None:
    with pytest.raises(PromptNotRedacted):
        check_prompt_redacted("call the parent on 98765 43210")
    check_prompt_redacted("[PHONE_1] and [STUDENT_2] are placeholders")  # must not raise


@pytest.mark.parametrize(("count", "sizes"), [(2, [2]), (3, [3]), (6, [3, 3]), (7, [3, 2, 2]), (10, [4, 3, 3])])
def test_dimension_grouping(rubric: Rubric, count: int, sizes: list[int]) -> None:
    dims = [rubric.dimensions[0]] * count
    assert [len(group) for group in group_dimensions(dims)] == sizes
