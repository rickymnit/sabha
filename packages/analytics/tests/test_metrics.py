"""Tests for sabha_analytics.metrics: deterministic numbers from a transcript and the segment map (P5.5).

Written before the implementation. Every expected value below was counted by hand from the fixture files in
fixtures/metrics/ (fictional Hinglish content); the comment next to each value shows the count. Times are ms on the
original timeline. Rounding: shares to 4 decimals, words per minute to 1 decimal, seconds are ms / 1000.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from sabha_analytics.metrics import (
    LONG_SILENCE_MS,
    RUBRIC_KEY_ALIASES,
    TURN_GAP_MS,
    Metric,
    available_metric_keys,
    compute_metrics,
    count_questions,
    is_open_question,
    is_question,
    role_turns,
    select_metrics,
    split_sentences,
)
from sabha_analytics.rubric import load_rubric
from sabha_core.timemap import SegmentMap, stats

FIXTURES = Path(__file__).parent / "fixtures" / "metrics"
RUBRICS = Path(__file__).resolve().parents[3] / "rubrics"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def run(fixture: dict[str, Any]) -> tuple[Metric, ...]:
    segment_map = SegmentMap.from_records(fixture["segments"])
    return compute_metrics(
        fixture["transcript"],
        primary_role=fixture["primary_role"],
        roles=fixture["roles"],
        segment_map=segment_map,
        segment_stats=stats(segment_map, fixture["total_ms"]),
    )


def values(name: str) -> dict[str, int | float | None]:
    return {metric.key: metric.value for metric in run(load(name))}


# --- the five hand-counted fixtures ----------------------------------------------------------------------------


def test_reception_call() -> None:
    assert values("reception_call") == {
        "duration_s": 60.0,  # total 60000 ms
        # silences: lead 800, 26000-17300 = 8700, 47000-40300 = 6700, tail 60000-58300 = 1700 -> 17900 / 60000
        "silence_share": 0.2983,
        "longest_silence_s": 8.7,  # the hold, 8700 ms
        "long_silence_count": 2,  # gaps between segments over 5 s: 8700 and 6700 (lead and tail are not gaps)
        # receptionist 5000 + 5500 + 10500 + 7500 = 28500; caller 4500 + 3000 + 3000 = 10500; both 39000
        "receptionist_talk_share": 0.7308,  # 28500 / 39000 = 0.73077
        "receptionist_turn_count": 4,  # R C R C R C R
        # "...kya help kar sakti hoon?", "...kis class mein hai?", "Aur kuch poochna hai aapko?"
        "receptionist_question_count": 3,
        "caller_talk_share": 0.2692,  # 10500 / 39000 = 0.26923
        "caller_turn_count": 3,
        "caller_question_count": 1,  # "Form kab milega?"
        "open_question_count": 0,  # no why/how/explain/kyun/kaise
        "open_question_ratio": 0.0,  # 0 / 3
        "words_per_minute": 149.5,  # words 19 + 16 + 22 + 14 = 71 in 28500 ms: 71 * 60000 / 28500 = 149.47
        "longest_monologue_s": 10.5,  # every receptionist turn is one utterance; the longest is [29500, 40000)
        "longest_monologue_start_ms": 29_500,
        "longest_monologue_end_ms": 40_000,
    }


def test_lesson_with_devanagari_questions() -> None:
    assert values("lesson_devanagari") == {
        "duration_s": 50.0,
        "silence_share": 0.094,  # one segment [0, 45300): tail silence 4700 / 50000
        "longest_silence_s": 4.7,  # the tail
        "long_silence_count": 0,  # one segment, so no gaps
        # teacher 8000 + 9500 + 9500 + 8500 = 35500; students 1500 + 2500 + 2500 = 6500; both 42000
        "teacher_talk_share": 0.8452,  # 35500 / 42000 = 0.84524
        "teacher_turn_count": 4,  # T S T S T S T
        # 1 "... एक slice कितना हुआ?" (recall); 2 "अब बताओ यह क्यों ... है।" (open, no "?"), "समझ आया" (recall);
        # 3 "... कैसे दिखाएंगे?" (open), "कौन board पर आएगा" (recall, no "?"); 4 "..., kya hoga agar ..." (open)
        "teacher_question_count": 6,
        "students_talk_share": 0.1548,  # 6500 / 42000 = 0.15476
        "students_turn_count": 3,
        "students_question_count": 1,  # "क्या हम copy में लिखें?"; "क्योंकि ..." (because) is not a question
        "open_question_count": 3,  # क्यों, कैसे, kya hoga
        "open_question_ratio": 0.5,  # 3 / 6
        "words_per_minute": 91.3,  # words 15 + 11 + 13 + 15 = 54 in 35500 ms: 54 * 60000 / 35500 = 91.27
        "longest_monologue_s": 9.5,  # two turns of 9500 ms tie; the earlier one wins
        "longest_monologue_start_ms": 10_500,
        "longest_monologue_end_ms": 20_000,
    }


def test_lesson_with_overlapping_speech() -> None:
    assert values("lesson_overlap") == {
        "duration_s": 25.0,
        "silence_share": 0.148,  # one segment [0, 21300): tail 3700 / 25000
        "longest_silence_s": 3.7,
        "long_silence_count": 0,
        # Overlap counts in full for every role speaking. teacher [0,10000) + [11000,20000) = 19000;
        # students [6000,8000) + [9000,12000) + [19000,21000) = 7000; shares are of 19000 + 7000 = 26000
        "teacher_talk_share": 0.7308,  # 19000 / 26000 = 0.73077
        "teacher_turn_count": 2,  # order T S S T S: the two student utterances (gap 1000 ms) are one turn
        "teacher_question_count": 2,  # "Why do plants need sunlight?", "How many leaves does this plant have?"
        "students_talk_share": 0.2692,  # 7000 / 26000 = 0.26923
        "students_turn_count": 2,
        "students_question_count": 0,
        "open_question_count": 1,  # "Why ..."; "How many ..." is recall
        "open_question_ratio": 0.5,  # 1 / 2
        "words_per_minute": 72.6,  # words 10 + 13 = 23 in 19000 ms: 23 * 60000 / 19000 = 72.63
        "longest_monologue_s": 10.0,  # [0, 10000) beats [11000, 20000) = 9000; the backchannel at 6000 ends it
        "longest_monologue_start_ms": 0,
        "longest_monologue_end_ms": 10_000,
    }


def test_lesson_with_long_monologue_split_by_short_pauses() -> None:
    assert values("lesson_long_monologue") == {
        "duration_s": 60.0,
        # gaps 14300-12300 = 2000, 32800-30300 = 2500, 47000-40300 = 6700, tail 60000-55300 = 4700 -> 15900
        "silence_share": 0.265,  # 15900 / 60000
        "longest_silence_s": 6.7,
        "long_silence_count": 1,  # only 6700 is over 5 s
        # teacher 12000 + 15700 + 7200 + 3000 + 2500 = 40400; students 1500; both 41900
        "teacher_talk_share": 0.9642,  # 40400 / 41900 = 0.96420
        # gaps 2300 and 2800 (< 3000) join the first three utterances; 7000 starts a new turn; the student ends it
        "teacher_turn_count": 3,
        "teacher_question_count": 1,  # "Baadal kaise bante hain" (no "?")
        "students_talk_share": 0.0358,  # 1500 / 41900 = 0.03580
        "students_turn_count": 1,
        "students_question_count": 0,
        "open_question_count": 1,  # kaise
        "open_question_ratio": 1.0,
        "words_per_minute": 65.3,  # words 11 + 15 + 11 + 3 + 4 = 44 in 40400 ms: 44 * 60000 / 40400 = 65.35
        "longest_monologue_s": 40.0,  # [0, 40000): three utterances joined across pauses of 2300 and 2800 ms
        "longest_monologue_start_ms": 0,
        "longest_monologue_end_ms": 40_000,
    }


def test_lesson_with_no_questions() -> None:
    assert values("lesson_no_questions") == {
        "duration_s": 30.0,
        "silence_share": 0.15,  # one segment [800, 26300): lead 800 + tail 3700 = 4500 / 30000
        "longest_silence_s": 3.7,
        "long_silence_count": 0,
        "teacher_talk_share": 1.0,  # students never speak
        "teacher_turn_count": 1,  # four utterances 500 ms apart
        # "Kabhi" is not "kab", "kahani" is not "kahan", "kyaari" is not "kya", "how" is not sentence-initial,
        # "Kya baat hai!" ends in "!", and "right"/"na" without "?" are not tags
        "teacher_question_count": 0,
        "students_talk_share": 0.0,
        "students_turn_count": 0,
        "students_question_count": 0,
        "open_question_count": 0,
        "open_question_ratio": None,  # no questions, so no ratio (not 0)
        "words_per_minute": 97.0,  # words 11 + 14 + 9 + 4 = 38 in 23500 ms: 38 * 60000 / 23500 = 97.02
        "longest_monologue_s": 25.0,  # [1000, 26000)
        "longest_monologue_start_ms": 1000,
        "longest_monologue_end_ms": 26_000,
    }


# --- metric records --------------------------------------------------------------------------------------------


def test_every_metric_has_unit_and_definition() -> None:
    for metric in run(load("reception_call")):
        assert metric.unit
        assert len(metric.definition) > 10
        assert metric.to_record() == {
            "key": metric.key,
            "value": metric.value,
            "unit": metric.unit,
            "definition": metric.definition,
        }


def test_metric_is_frozen() -> None:
    metric = run(load("reception_call"))[0]
    with pytest.raises(AttributeError):
        metric.value = 1  # type: ignore[misc]  # assigning to a frozen dataclass is the point of the test


def test_no_metric_names_a_speaker() -> None:
    # Golden rule 10: student and caller numbers are per role, never per speaker. lesson_devanagari and
    # lesson_overlap have two student speaker labels; neither appears in any key, and both count as one role.
    for name in ("lesson_devanagari", "lesson_overlap"):
        for metric in run(load(name)):
            assert "SPEAKER" not in metric.key.upper()


def test_speaker_labels_do_not_change_any_number() -> None:
    fixture = load("lesson_overlap")
    relabelled = copy.deepcopy(fixture)
    for index, utterance in enumerate(relabelled["transcript"]["utterances"]):
        utterance["speaker_label"] = f"X{index}"
    assert run(relabelled) == run(fixture)


# --- rubric keys -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rubric_file", "fixture_name"),
    [("teaching.school.v0.1.yaml", "lesson_devanagari"), ("reception.school.v0.1.yaml", "reception_call")],
)
def test_rubric_metrics_are_all_computed(rubric_file: str, fixture_name: str) -> None:
    rubric, _ = load_rubric(RUBRICS / rubric_file)
    assert set(rubric.computed_metrics) <= available_metric_keys(rubric.roles)
    selected = select_metrics(run(load(fixture_name)), rubric.computed_metrics)
    assert tuple(metric.key for metric in selected) == rubric.computed_metrics


def test_call_duration_is_an_alias_for_duration() -> None:
    assert RUBRIC_KEY_ALIASES["call_duration_s"] == "duration_s"
    (metric,) = select_metrics(run(load("reception_call")), ["call_duration_s"])
    assert (metric.key, metric.value, metric.unit) == ("call_duration_s", 60.0, "s")


def test_select_unknown_metric_fails() -> None:
    with pytest.raises(KeyError, match="teacher_happiness"):
        select_metrics(run(load("reception_call")), ["teacher_happiness"])


def test_available_keys_follow_the_roles() -> None:
    keys = available_metric_keys(("receptionist", "caller"))
    assert {"receptionist_talk_share", "caller_talk_share", "call_duration_s", "long_silence_count"} <= keys
    assert "teacher_talk_share" not in keys


# --- question rules --------------------------------------------------------------------------------------------


def test_split_sentences() -> None:
    assert split_sentences("Theek hai. Aur kuch? Haan! अच्छा। ठीक") == (
        "Theek hai.",
        "Aur kuch?",
        "Haan!",
        "अच्छा।",
        "ठीक",
    )
    assert split_sentences("  ") == ()


@pytest.mark.parametrize(
    "sentence",
    [
        "Sab clear hai?",
        "Yeh sahi hai na?",  # tag question: has "?"
        "Answer 5 hai, right?",
        "Photosynthesis kya hai",  # Hindi marker, no "?"
        "Tum kab aaoge",
        "Kahaan rakha hai",
        "Samajh aaya",
        "समझ आया",
        "यह क्यों होता है।",
        "Kitne slices bache",
        "What is a fraction",  # English wh-word first
        "Kya?!",
    ],
)
def test_questions(sentence: str) -> None:
    assert is_question(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Theek hai, aage badhte hain.",
        "Kya baat hai!",  # exclamation
        "Yeh bhool na jaana.",  # "na" without "?"
        "Right side mein likho.",
        "This is how we add.",  # "how" not first
        "क्योंकि आठ टुकड़े हैं",  # because, not why
        "Kabhi kabhi aisa hota hai.",
        "",
    ],
)
def test_not_questions(sentence: str) -> None:
    assert not is_question(sentence)


def test_known_false_positives_are_counted() -> None:
    # Documented limitation, kept visible here: an embedded "kya"/"kaise" in a statement counts as a question.
    assert is_question("Dekho maine kya likha board pe.")
    assert is_question("Main dikhata hoon kaise karte hain.")


@pytest.mark.parametrize(
    ("sentence", "is_open"),
    [
        ("Why is the sky blue?", True),
        ("How does it work?", True),
        ("How many sides does it have?", False),
        ("How much is left?", False),
        ("Can you explain this step?", True),
        ("Batao kyun?", True),
        ("Yeh kaise hua?", True),
        ("Kyon aisa hota hai", True),
        ("What if we double it?", True),
        ("Andhere mein rakhein toh kya hoga?", True),
        ("Ise samjhao?", True),
        ("यह कैसे हुआ?", True),
        ("अगर पानी न हो तो क्या होगा?", True),
        ("Photosynthesis kya hai?", False),
        ("Samajh aaya?", False),
        ("What is 2 plus 3?", False),
    ],
)
def test_open_or_recall(sentence: str, is_open: bool) -> None:
    assert is_question(sentence)
    assert is_open_question(sentence) is is_open


def test_count_questions_per_sentence() -> None:
    assert count_questions("Kya hai yeh? Aur kyun? Theek hai.") == (2, 1)
    assert count_questions("Chalo shuru karte hain.") == (0, 0)


# --- turns and thresholds --------------------------------------------------------------------------------------


def utterance(role: str, start: int, end: int, text: str = "haan") -> dict[str, Any]:
    return {
        "role": role,
        "speaker_label": "A",
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "avg_confidence": 0.9,
        "low_confidence_spans": [],
    }


def test_turn_gap_threshold() -> None:
    assert TURN_GAP_MS == 3000
    just_under = [utterance("teacher", 0, 1000), utterance("teacher", 1000 + TURN_GAP_MS - 1, 5000)]
    at_threshold = [utterance("teacher", 0, 1000), utterance("teacher", 1000 + TURN_GAP_MS, 5000)]
    assert [(t.start_ms, t.end_ms) for t in role_turns(just_under)] == [(0, 5000)]
    assert [(t.start_ms, t.end_ms) for t in role_turns(at_threshold)] == [(0, 1000), (4000, 5000)]


def test_another_role_ends_a_turn() -> None:
    turns = role_turns(
        [utterance("teacher", 0, 1000), utterance("students", 1100, 1200), utterance("teacher", 1300, 2000)]
    )
    assert [(t.role, t.start_ms, t.end_ms) for t in turns] == [
        ("teacher", 0, 1000),
        ("students", 1100, 1200),
        ("teacher", 1300, 2000),
    ]


def transcript(*utterances: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "transcript@v1",
        "timeline": "original",
        "asr_model": "fixture/none",
        "word_count": len(utterances),
        "utterances": list(utterances),
    }


def by_key(metrics: tuple[Metric, ...]) -> dict[str, int | float | None]:
    return {metric.key: metric.value for metric in metrics}


def test_long_silence_threshold_is_strictly_over_five_seconds() -> None:
    assert LONG_SILENCE_MS == 5000
    exactly = SegmentMap.from_records(
        [
            {"orig_start_ms": 0, "orig_end_ms": 1000, "compact_start_ms": 0},
            {"orig_start_ms": 6000, "orig_end_ms": 7000, "compact_start_ms": 1000},  # gap 5000: not long
            {"orig_start_ms": 12_001, "orig_end_ms": 13_000, "compact_start_ms": 2000},  # gap 5001: long
        ]
    )
    doc = transcript(
        utterance("teacher", 0, 1000), utterance("teacher", 6000, 7000), utterance("teacher", 12_001, 13_000)
    )
    result = by_key(
        compute_metrics(doc, primary_role="teacher", segment_map=exactly, segment_stats=stats(exactly, 13_000))
    )
    assert result["long_silence_count"] == 1


def test_empty_transcript_gives_no_ratios() -> None:
    empty = SegmentMap(())
    result = by_key(
        compute_metrics(transcript(), primary_role="teacher", segment_map=empty, segment_stats=stats(empty, 10_000))
    )
    assert result["teacher_talk_share"] is None
    assert result["words_per_minute"] is None
    assert result["longest_monologue_s"] is None
    assert result["longest_monologue_start_ms"] is None
    assert result["silence_share"] == 1.0
    assert result["teacher_turn_count"] == 0


def test_roles_default_to_primary_then_transcript_roles() -> None:
    fixture = load("reception_call")
    segment_map = SegmentMap.from_records(fixture["segments"])
    keys = [
        m.key
        for m in compute_metrics(
            fixture["transcript"],
            primary_role="receptionist",
            segment_map=segment_map,
            segment_stats=stats(segment_map, fixture["total_ms"]),
        )
    ]
    assert keys.index("receptionist_talk_share") < keys.index("caller_talk_share")


# --- bad input -------------------------------------------------------------------------------------------------


def test_role_outside_the_rubric_roles_fails() -> None:
    fixture = load("lesson_overlap")
    fixture["roles"] = ["teacher", "caller"]
    with pytest.raises(ValueError, match="students"):
        run(fixture)


def test_primary_role_must_be_one_of_the_roles() -> None:
    fixture = load("lesson_overlap")
    fixture["primary_role"] = "receptionist"
    with pytest.raises(ValueError, match="receptionist"):
        run(fixture)


def test_stats_must_match_the_segment_map() -> None:
    fixture = load("lesson_overlap")
    segment_map = SegmentMap.from_records(fixture["segments"])
    wrong = dict(stats(segment_map, fixture["total_ms"]))
    wrong["speech_ms"] = 1
    with pytest.raises(ValueError, match="segment stats"):
        compute_metrics(
            fixture["transcript"],
            primary_role="teacher",
            segment_map=segment_map,
            segment_stats=wrong,  # type: ignore[arg-type]  # a plain dict standing in for SegmentStats
        )


def test_utterance_past_the_end_of_the_recording_fails() -> None:
    fixture = load("lesson_overlap")
    fixture["total_ms"] = 21_300  # speech ends at 21300; the last utterance ends at 21000, so make one later
    fixture["transcript"]["utterances"][-1]["end_ms"] = 22_000
    with pytest.raises(ValueError, match="after the end"):
        run(fixture)


def test_invalid_transcript_fails() -> None:
    fixture = load("lesson_overlap")
    fixture["transcript"]["timeline"] = "compact"
    with pytest.raises(ValueError, match="timeline"):
        run(fixture)
