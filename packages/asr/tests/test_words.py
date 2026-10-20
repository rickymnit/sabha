"""Tests for sabha_asr.words: the Word and Turn contracts and the rule that gives each word to one speaker turn.

The assignment rule decides who said every word of the transcript, so its tie and no-overlap rules are pinned here.
"""

from __future__ import annotations

import math
import random
from typing import Any

import pytest

from sabha_asr.words import Turn, Word, assign_words_to_turns


def word(start_ms: int, end_ms: int, text: str = "x", confidence: float = 0.9) -> Word:
    return Word(text=text, start_ms=start_ms, end_ms=end_ms, confidence=confidence)


# --- Word ------------------------------------------------------------------------------------------------------


def test_word_strips_text_and_stores_confidence_as_float() -> None:
    w = Word(text="  namaste ", start_ms=0, end_ms=400, confidence=1)
    assert w.text == "namaste"
    assert isinstance(w.confidence, float)
    assert w.duration_ms == 400


def test_zero_length_word_is_allowed() -> None:
    assert word(500, 500).duration_ms == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"text": "   "},
        {"text": ""},
        {"start_ms": -1},
        {"start_ms": 600, "end_ms": 500},
        {"start_ms": 1.5},
        {"end_ms": True},
        {"confidence": 1.01},
        {"confidence": -0.1},
        {"confidence": math.nan},
        {"confidence": True},
        {"confidence": "0.5"},
    ],
)
def test_word_rejects_bad_values(kwargs: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"text": "x", "start_ms": 0, "end_ms": 500, "confidence": 0.5, **kwargs}
    with pytest.raises(ValueError):
        Word(**fields)


def test_word_without_confidence_is_allowed_and_round_trips() -> None:
    # Sarvam gives no word confidence (ADR 0006); the key stays, with null.
    w = Word("haan", 10, 20, None)
    assert w.confidence is None
    assert w.to_record() == {"text": "haan", "start_ms": 10, "end_ms": 20, "confidence": None}
    assert Word.from_record(w.to_record()) == w
    assert w.shifted(5).confidence is None


def test_word_record_round_trip() -> None:
    w = word(10, 20, "haan", 0.75)
    assert Word.from_record(w.to_record()) == w
    with pytest.raises(ValueError, match="keys"):
        Word.from_record({**w.to_record(), "speaker": "A"})
    with pytest.raises(ValueError, match="object"):
        Word.from_record(["haan", 10, 20, 0.75])


def test_shifted_moves_both_ends() -> None:
    assert word(10, 20).shifted(1000) == word(1010, 1020)


# --- Turn ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "start", "end"),
    [("A", 100, 100), ("A", 200, 100), ("A", -5, 10), ("", 0, 10), ("  ", 0, 10)],
)
def test_turn_rejects_bad_values(label: str, start: int, end: int) -> None:
    with pytest.raises(ValueError):
        Turn(speaker_label=label, start_ms=start, end_ms=end)


def test_turn_record_round_trip() -> None:
    t = Turn("SPEAKER_00", 0, 1000)
    assert Turn.from_record({"speaker_label": "SPEAKER_00", "start_ms": 0, "end_ms": 1000}) == t
    with pytest.raises(ValueError):
        Turn.from_record({"speaker_label": "SPEAKER_00", "start_ms": 0})


# --- assign_words_to_turns -------------------------------------------------------------------------------------

A = Turn("A", 0, 1000)
B = Turn("B", 1000, 2000)


def test_word_goes_to_turn_with_largest_overlap() -> None:
    # [900, 1300) overlaps A by 100 ms and B by 300 ms.
    assert assign_words_to_turns([word(900, 1300)], [A, B]) == [B]
    assert assign_words_to_turns([word(700, 1100)], [A, B]) == [A]


def test_equal_overlap_goes_to_the_earlier_turn() -> None:
    assert assign_words_to_turns([word(900, 1100)], [B, A]) == [A]


def test_word_inside_two_overlapping_turns_goes_to_the_one_that_started_first() -> None:
    # Overlapping speech: B interrupts A. A word fully inside both belongs to the speaker who had the floor.
    a = Turn("A", 0, 3000)
    b = Turn("B", 1000, 2500)
    assert assign_words_to_turns([word(1200, 1500)], [b, a]) == [a]


def test_word_with_no_overlapping_turn_goes_to_the_nearest_turn() -> None:
    a = Turn("A", 0, 2000)
    b = Turn("B", 3000, 4000)
    assert assign_words_to_turns([word(2100, 2200)], [a, b]) == [a]  # 100 ms after A, 800 ms before B
    assert assign_words_to_turns([word(2500, 2900)], [a, b]) == [b]  # 500 ms after A, 100 ms before B
    assert assign_words_to_turns([word(2300, 2700)], [a, b]) == [a]  # 300 ms either way: the earlier turn
    assert assign_words_to_turns([word(4500, 4600)], [a, b]) == [b]  # after every turn
    assert assign_words_to_turns([word(0, 0)], [b]) == [b]  # before every turn


def test_zero_length_word_is_treated_as_one_millisecond() -> None:
    # Half-open turns: time 1000 belongs to B, not A.
    assert assign_words_to_turns([word(1000, 1000)], [A, B]) == [B]
    assert assign_words_to_turns([word(999, 999)], [A, B]) == [A]


def test_no_words_and_no_turns() -> None:
    assert assign_words_to_turns([], []) == []
    with pytest.raises(ValueError, match="no turns"):
        assign_words_to_turns([word(0, 10)], [])


def test_assignment_matches_brute_force_on_random_input() -> None:
    rng = random.Random(7)  # noqa: S311  # test data, not security
    turns = []
    for _ in range(60):
        start = rng.randrange(0, 60_000)
        turns.append(Turn(rng.choice("ABC"), start, start + rng.randrange(1, 8000)))
    words = []
    for _ in range(400):
        start = rng.randrange(0, 70_000)
        words.append(word(start, start + rng.randrange(0, 900)))

    def brute(w: Word) -> Turn:
        start, end = w.start_ms, max(w.end_ms, w.start_ms + 1)
        key = sorted(turns, key=lambda t: (t.start_ms, t.end_ms, t.speaker_label))
        overlaps = [(min(end, t.end_ms) - max(start, t.start_ms), -i, t) for i, t in enumerate(key)]
        best = max(overlaps, key=lambda o: (o[0], o[1]))
        if best[0] > 0:
            return best[2]
        distances = [(max(t.start_ms - end, start - t.end_ms), i, t) for i, t in enumerate(key)]
        return min(distances, key=lambda d: (d[0], d[1]))[2]

    assert assign_words_to_turns(words, turns) == [brute(w) for w in words]
