"""Role accuracy and role-level DER (P4.3): hand-computed cases."""

from __future__ import annotations

import pytest
from evaldata import Span
from roles import RoleCounts, score_roles


def ref(role: str, start_s: float, end_s: float) -> Span:
    return Span(start_ms=int(start_s * 1000), end_ms=int(end_s * 1000), role=role, speaker=role, text="")


def hyp(speaker: str, role: str, start_s: float, end_s: float) -> Span:
    return Span(start_ms=int(start_s * 1000), end_ms=int(end_s * 1000), role=role, speaker=speaker, text="")


def test_perfect_match() -> None:
    c = score_roles([ref("teacher", 0, 10), ref("students", 10, 15)],
                    [hyp("S0", "teacher", 0, 10), hyp("S1", "students", 10, 15)])  # fmt: skip
    assert c.role_accuracy == 1.0
    assert c.der == 0.0


def test_swapped_roles_fail_role_accuracy_but_not_der() -> None:
    # The diarizer separated the voices perfectly; only the role labels are wrong.
    c = score_roles([ref("teacher", 0, 10), ref("students", 10, 15)],
                    [hyp("S0", "students", 0, 10), hyp("S1", "teacher", 10, 15)])  # fmt: skip
    assert c.role_accuracy == 0.0
    assert c.der == 0.0


def test_missed_speech_counts_against_both() -> None:
    c = score_roles([ref("teacher", 0, 10)], [hyp("S0", "teacher", 0, 5)])
    assert c.role_accuracy == pytest.approx(0.5)
    assert c.missed_ms == 5000
    assert c.der == pytest.approx(0.5)


def test_speech_in_gold_silence_is_a_false_alarm_for_der_only() -> None:
    c = score_roles([ref("teacher", 0, 10)], [hyp("S0", "teacher", 0, 10), hyp("S0", "teacher", 12, 14)])
    assert c.role_accuracy == 1.0
    assert c.false_alarm_ms == 2000
    assert c.der == pytest.approx(0.2)


def test_several_system_speakers_can_map_to_the_students_group() -> None:
    c = score_roles(
        [ref("teacher", 0, 10), ref("students", 10, 20)],
        [hyp("S0", "teacher", 0, 10), hyp("S1", "students", 10, 15), hyp("S2", "students", 15, 20)],
    )
    assert c.der == 0.0
    assert c.role_accuracy == 1.0


def test_speaker_confusion_inside_one_system_speaker() -> None:
    # S0 is mostly the teacher (8 s) but also swallowed 2 s of students: those 2 s are confusion.
    c = score_roles([ref("teacher", 0, 8), ref("students", 8, 10)], [hyp("S0", "teacher", 0, 10)])
    assert c.confusion_ms == 2000
    assert c.der == pytest.approx(0.2)
    assert c.role_accuracy == pytest.approx(0.8)


def test_overlapping_reference_speech() -> None:
    # Teacher and students talk over each other for 2 s; the system heard only the teacher there.
    c = score_roles([ref("teacher", 0, 10), ref("students", 8, 12)],
                    [hyp("S0", "teacher", 0, 10), hyp("S1", "students", 10, 12)])  # fmt: skip
    assert c.ref_ms == 14000  # 10 s teacher + 4 s students
    assert c.missed_ms == 2000
    assert c.role_accuracy == pytest.approx(12 / 14)


def test_no_reference_speech_gives_no_scores() -> None:
    c = score_roles([], [hyp("S0", "teacher", 0, 5)])
    assert c.role_accuracy is None
    assert c.der is None


def test_counts_add_up() -> None:
    c = RoleCounts(ref_ms=100, correct_role_ms=60, missed_ms=10, false_alarm_ms=5, confusion_ms=20)
    assert c.der == pytest.approx(0.35)
    assert c.role_accuracy == pytest.approx(0.6)
