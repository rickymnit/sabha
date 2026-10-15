"""Tests for sabha_asr.roles: who is the teacher or receptionist, by heuristics only (P3.6).

Low confidence must be flagged for review, never guessed silently. Students are a group role: every non-teacher
speaker in a lesson gets the same "students" role.
"""

from __future__ import annotations

import json

import pytest

from sabha_asr.roles import (
    DEFAULT_LONG_TURN_MS,
    DEFAULT_MIN_CONFIDENCE,
    METHOD_CHANNEL,
    METHOD_HEURISTIC,
    METHOD_LOW_CONFIDENCE,
    REASON_UNCLEAR_ROLES,
    RoleAssignment,
    RoleParams,
    SpeakerRole,
    TieBreakRequest,
    assign_roles,
    next_status,
    normalise_text,
)
from sabha_asr.words import Turn, Word
from sabha_core.state import RecordingStatus, check_transition

TEACHING_ROLES = ("teacher", "students")
RECEPTION_ROLES = ("receptionist", "caller")
SCHOOL_NAMES = ("Sunrise Public School", "Sunrise School")


def script(lines: list[tuple[str, int, str]], gap_ms: int = 200) -> tuple[list[Turn], list[Word]]:
    """Turns spoken one after another with `gap_ms` between them; each turn's words spread evenly over it."""
    turns, words, t = [], [], 0
    for speaker, duration_ms, text in lines:
        turns.append(Turn(speaker, t, t + duration_ms))
        tokens = text.split() or ["mm"]
        step = duration_ms // len(tokens)
        for i, token in enumerate(tokens):
            words.append(Word(token, t + i * step, t + i * step + max(step - 50, 1), 0.9))
        t += duration_ms + gap_ms
    return turns, words


def roles_of(assignment: RoleAssignment) -> dict[str, str]:
    return {label: speaker.role for label, speaker in assignment.speakers.items()}


def test_defaults() -> None:
    assert DEFAULT_LONG_TURN_MS == 15_000
    assert DEFAULT_MIN_CONFIDENCE == 0.7


# --- teaching --------------------------------------------------------------------------------------------------


def test_clear_teacher() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 40_000, "aaj hum photosynthesis padhenge"),
            ("SPEAKER_01", 3_000, "ma'am question"),
            ("SPEAKER_00", 25_000, "haan batao"),
            ("SPEAKER_02", 2_000, "chlorophyll"),
            ("SPEAKER_00", 18_000, "bilkul sahi"),
            ("SPEAKER_01", 4_000, "sunlight"),
            ("SPEAKER_00", 30_000, "ab diagram dekho"),
        ]
    )
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert roles_of(result) == {"SPEAKER_00": "teacher", "SPEAKER_01": "students", "SPEAKER_02": "students"}
    assert result.needs_review_reason is None
    assert next_status(result) is RecordingStatus.ANALYZING
    teacher = result.speakers["SPEAKER_00"]
    assert teacher.method == METHOD_HEURISTIC
    assert teacher.confidence == 1.0
    assert all(s.confidence == teacher.confidence for s in result.speakers.values())  # one decision, one confidence


def test_two_adult_classroom_needs_review() -> None:
    # Co-teaching or a visiting teacher: two speakers with near-equal talk and long turns.
    turns, words = script(
        [
            ("SPEAKER_00", 30_000, "good morning class"),
            ("SPEAKER_01", 28_000, "today I will help"),
            ("SPEAKER_00", 22_000, "open your books"),
            ("SPEAKER_01", 22_000, "page fifty"),
            ("SPEAKER_02", 3_000, "yes ma'am"),
        ]
    )
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES
    assert all(s.method == METHOD_LOW_CONFIDENCE for s in result.speakers.values())
    assert all(s.confidence < DEFAULT_MIN_CONFIDENCE for s in result.speakers.values())
    assert list(roles_of(result).values()).count("teacher") == 1  # a best guess is still recorded for the reviewer
    status = next_status(result)
    assert status is RecordingStatus.NEEDS_REVIEW
    check_transition(RecordingStatus.TRANSCRIBING, status)


def test_heuristics_disagreeing_is_low_confidence() -> None:
    # SPEAKER_00 talks most, in medium turns; SPEAKER_01 has the only long turns.
    turns, words = script(
        [("SPEAKER_00", 12_000, "a")] * 3
        + [("SPEAKER_01", 16_000, "b"), ("SPEAKER_00", 12_000, "a"), ("SPEAKER_01", 16_000, "b")]
        + [("SPEAKER_00", 12_000, "a")] * 2,
        gap_ms=1_500,  # gaps longer than the join gap: the medium turns stay separate
    )
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES
    assert roles_of(result)["SPEAKER_00"] == "teacher"  # the guess follows talk share
    assert result.speakers["SPEAKER_00"].confidence == 0.5


def test_single_speaker_recording() -> None:
    turns, words = script([("SPEAKER_00", 40_000, "explaining"), ("SPEAKER_00", 20_000, "more")])
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert roles_of(result) == {"SPEAKER_00": "teacher"}
    assert result.needs_review_reason is None


def test_single_speaker_without_long_turns_needs_review() -> None:
    turns, words = script([("SPEAKER_00", 5_000, "hello")])
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert roles_of(result) == {"SPEAKER_00": "teacher"}
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


def test_fragmented_teacher_turns_are_joined_before_counting_long_turns() -> None:
    # The diarizer split each of the teacher's long explanations into 8 s pieces with short gaps.
    lines = [("SPEAKER_00", 8_000, "x")] * 3 + [("SPEAKER_01", 2_000, "y")] + [("SPEAKER_00", 8_000, "x")] * 3
    turns, words = script(lines, gap_ms=300)
    assert assign_roles(turns, words, "teaching", TEACHING_ROLES).needs_review_reason is None
    strict = RoleParams(turn_join_gap_ms=0)
    assert assign_roles(turns, words, "teaching", TEACHING_ROLES, params=strict).needs_review_reason is not None


def test_confidence_grows_with_the_talk_share_margin() -> None:
    def confidence(student_ms: int) -> float:
        turns, words = script([("T", 40_000, "a"), ("S", student_ms, "b"), ("T", 20_000, "c")])
        return assign_roles(turns, words, "teaching", TEACHING_ROLES).speakers["T"].confidence

    # Long turns: T 2, S 1, so the long-turn score is (2 - 1) / 2 = 0.5 in both cases.
    # Shares 60/90 vs 30/90: margin 0.333 >= 0.30, full credit. 60/100 vs 40/100: margin 0.2, credit 0.2 / 0.3.
    assert confidence(30_000) == 0.5 + 0.25 * 1 + 0.25 * 0.5
    assert confidence(40_000) == pytest.approx(0.5 + 0.25 * (0.2 / 0.3) + 0.25 * 0.5, abs=1e-3)


def test_no_turns_needs_review() -> None:
    result = assign_roles([], [], "teaching", TEACHING_ROLES)
    assert result.speakers == {}
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


# --- reception -------------------------------------------------------------------------------------------------


def test_reception_call_with_greeting() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 4_000, "Namaste, Sunrise Public School se Priya bol rahi hoon."),
            ("SPEAKER_01", 3_000, "Hello ji, admission ke baare mein puchna tha"),
            ("SPEAKER_00", 3_000, "Haan ji, kis class ke liye?"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=SCHOOL_NAMES)
    assert roles_of(result) == {"SPEAKER_00": "receptionist", "SPEAKER_01": "caller"}
    assert result.needs_review_reason is None
    assert result.speakers["SPEAKER_00"].confidence == 1.0  # greets with name, introduces herself, speaks first


def test_reception_outbound_call_receptionist_speaks_second() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 1_000, "Hello?"),
            ("SPEAKER_01", 4_000, "Hello, main Sunrise School se bol rahi hoon, fees ke baare mein"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=SCHOOL_NAMES)
    assert roles_of(result) == {"SPEAKER_00": "caller", "SPEAKER_01": "receptionist"}
    assert result.needs_review_reason is None
    assert result.speakers["SPEAKER_01"].confidence == 0.75


def test_reception_without_greeting_needs_review() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 2_000, "Haan ji boliye"),
            ("SPEAKER_01", 3_000, "Admission form kab milega"),
            ("SPEAKER_00", 3_000, "Kal se milega"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=SCHOOL_NAMES)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES
    assert roles_of(result) == {"SPEAKER_00": "receptionist", "SPEAKER_01": "caller"}  # guess: first speaker
    assert result.speakers["SPEAKER_00"].confidence == 0.5
    assert next_status(result) is RecordingStatus.NEEDS_REVIEW


def test_reception_greeting_in_devanagari() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 4_000, "नमस्ते, सनराइज़ स्कूल से बोल रही हूँ"),
            ("SPEAKER_01", 3_000, "जी, फीस के बारे में"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=("सनराइज़ स्कूल",))
    assert roles_of(result)["SPEAKER_00"] == "receptionist"
    assert result.needs_review_reason is None


def test_caller_repeating_the_school_name_lowers_confidence() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 3_000, "Good morning, Sunrise School"),
            ("SPEAKER_01", 3_000, "Hello, Sunrise School? admission ke liye"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=SCHOOL_NAMES)
    assert roles_of(result)["SPEAKER_00"] == "receptionist"
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


def test_greeting_after_the_window_does_not_count() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 2_000, "haan ji"),
            ("SPEAKER_01", 40_000, "lambi baat"),
            ("SPEAKER_00", 3_000, "Namaste Sunrise School"),
        ]
    )
    result = assign_roles(turns, words, "reception", RECEPTION_ROLES, tenant_name_variants=SCHOOL_NAMES)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


def test_stereo_channel_hint_wins() -> None:
    turns, words = script(
        [
            ("SPEAKER_00", 4_000, "Namaste, Sunrise Public School se bol rahi hoon"),
            ("SPEAKER_01", 3_000, "Hello"),
        ]
    )
    result = assign_roles(
        turns,
        words,
        "reception",
        RECEPTION_ROLES,
        tenant_name_variants=SCHOOL_NAMES,
        receptionist_channel_speaker="SPEAKER_01",
    )
    assert roles_of(result) == {"SPEAKER_00": "caller", "SPEAKER_01": "receptionist"}
    assert {s.method for s in result.speakers.values()} == {METHOD_CHANNEL}
    assert result.needs_review_reason is None


def test_channel_hint_for_unknown_speaker_is_an_error() -> None:
    turns, words = script([("SPEAKER_00", 4_000, "hello")])
    with pytest.raises(ValueError, match="SPEAKER_09"):
        assign_roles(turns, words, "reception", RECEPTION_ROLES, receptionist_channel_speaker="SPEAKER_09")
    with pytest.raises(ValueError, match="reception"):
        assign_roles(turns, words, "teaching", TEACHING_ROLES, receptionist_channel_speaker="SPEAKER_00")


def test_normalise_text_keeps_devanagari_marks() -> None:
    assert normalise_text("  Namaste!!  Sunrise-School,  ") == "namaste sunrise school"
    assert normalise_text("बोल रही हूँ।") == "बोल रही हूँ"


# --- inputs, output format and the tie-breaker hook ------------------------------------------------------------


@pytest.mark.parametrize(
    ("recording_type", "rubric_roles"),
    [
        ("meeting", TEACHING_ROLES),
        ("teaching", ("teacher",)),
        ("teaching", ("teacher", "teacher")),
        ("teaching", ("", "x")),
    ],
)
def test_bad_inputs_are_rejected(recording_type: str, rubric_roles: tuple[str, ...]) -> None:
    turns, words = script([("SPEAKER_00", 4_000, "hello")])
    with pytest.raises(ValueError):
        assign_roles(turns, words, recording_type, rubric_roles)


def test_roles_json_format() -> None:
    turns, words = script([("SPEAKER_00", 40_000, "a"), ("SPEAKER_01", 2_000, "b")])
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES)
    assert json.loads(result.to_json()) == {
        "SPEAKER_00": {"role": "teacher", "confidence": 1.0, "method": "heuristic"},
        "SPEAKER_01": {"role": "students", "confidence": 1.0, "method": "heuristic"},
    }
    assert result.role_by_speaker() == {"SPEAKER_00": "teacher", "SPEAKER_01": "students"}


def two_adults() -> tuple[list[Turn], list[Word]]:
    return script([("A", 30_000, "one two"), ("B", 29_000, "three four"), ("C", 2_000, "five")])


def test_tie_breaker_is_not_asked_when_heuristics_are_confident() -> None:
    def never(request: TieBreakRequest) -> RoleAssignment | None:
        raise AssertionError("should not be called")

    turns, words = script([("SPEAKER_00", 40_000, "a"), ("SPEAKER_01", 2_000, "b")])
    assign_roles(turns, words, "teaching", TEACHING_ROLES, tie_breaker=never)


def test_tie_breaker_can_settle_low_confidence() -> None:
    seen: list[TieBreakRequest] = []

    def decide(request: TieBreakRequest) -> RoleAssignment | None:
        seen.append(request)
        return RoleAssignment(
            {
                "A": SpeakerRole("students", 0.8, "llm"),
                "B": SpeakerRole("teacher", 0.8, "llm"),
                "C": SpeakerRole("students", 0.8, "llm"),
            }
        )

    turns, words = two_adults()
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES, tie_breaker=decide)
    assert result.role_by_speaker() == {"A": "students", "B": "teacher", "C": "students"}
    assert result.needs_review_reason is None
    (request,) = seen
    assert request.heuristic.needs_review_reason == REASON_UNCLEAR_ROLES
    assert request.opening[0] == ("A", "one two")
    assert request.rubric_roles == TEACHING_ROLES


def test_unsure_tie_breaker_leaves_it_for_review() -> None:
    turns, words = two_adults()
    result = assign_roles(turns, words, "teaching", TEACHING_ROLES, tie_breaker=lambda request: None)
    assert result.needs_review_reason == REASON_UNCLEAR_ROLES


def test_tie_breaker_answer_is_checked() -> None:
    def two_teachers(request: TieBreakRequest) -> RoleAssignment | None:
        return RoleAssignment({label: SpeakerRole("teacher", 0.9, "llm") for label in ("A", "B", "C")})

    turns, words = two_adults()
    with pytest.raises(ValueError, match="exactly one"):
        assign_roles(turns, words, "teaching", TEACHING_ROLES, tie_breaker=two_teachers)
