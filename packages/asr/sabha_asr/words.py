"""Words, speaker turns, and the rule that gives each word to one speaker turn (shared by P3.5, P3.6 and P3.7).

All times are integer milliseconds on the COMPACT timeline: ASR and diarization both run on compact.wav. Intervals
are half-open, [start_ms, end_ms), as in sabha_core.timemap. Only transcript assembly maps times back to the
original recording (golden rule 4).

Word-to-turn assignment (`assign_words_to_turns`):

- A word goes to the turn it overlaps for the most milliseconds.
- Equal overlap goes to the turn that started first (ties on start: the shorter turn, then the smaller speaker
  label). In overlapping speech that is the speaker who already had the floor, not the one interrupting.
- A word that overlaps no turn (diarization and ASR disagree a little at turn edges, or a word falls in a gap the
  diarizer left) goes to the nearest turn by gap length. Equal gaps go to the earlier turn.
- A zero-length word (some providers emit them) is treated as the 1 ms [start_ms, start_ms + 1), so a word exactly
  at a turn boundary belongs to the turn that starts there, as half-open intervals say.
"""

from __future__ import annotations

import math
import operator
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict, TypeGuard

_WORD_FIELDS = ("text", "start_ms", "end_ms", "confidence")
_TURN_FIELDS = ("speaker_label", "start_ms", "end_ms")


class WordRecord(TypedDict):
    """One word as stored in asr@v1.json."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float


class TurnRecord(TypedDict):
    """One diarization turn as stored in the diarization output."""

    speaker_label: str
    start_ms: int
    end_ms: int


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class Word:
    """One recognised word, [start_ms, end_ms), with the ASR's confidence in [0, 1].

    Leading and trailing whitespace is stripped from `text` (some providers prefix words with a space); text that is
    blank after stripping is refused, so provider adapters must drop empty tokens. `confidence` is stored as float.
    Zero-length words (start_ms == end_ms) are allowed.
    """

    text: str
    start_ms: int
    end_ms: int
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(f"word text must be a non-blank string: {self!r}")
        if not (_is_int(self.start_ms) and _is_int(self.end_ms)):
            raise ValueError(f"word times must be whole milliseconds (int): {self!r}")
        if not 0 <= self.start_ms <= self.end_ms:
            raise ValueError(f"word times must satisfy 0 <= start_ms <= end_ms: {self!r}")
        if not _is_number(self.confidence) or math.isnan(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError(f"word confidence must be a number in [0, 1]: {self!r}")
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "confidence", float(self.confidence))

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def shifted(self, offset_ms: int) -> Word:
        """The same word moved by `offset_ms` (for example from chunk-relative to compact time)."""
        offset_ms = operator.index(offset_ms)
        return Word(self.text, self.start_ms + offset_ms, self.end_ms + offset_ms, self.confidence)

    def to_record(self) -> WordRecord:
        return {"text": self.text, "start_ms": self.start_ms, "end_ms": self.end_ms, "confidence": self.confidence}

    @classmethod
    def from_record(cls, record: object) -> Word:
        """Build a word from an asr@v1.json entry. Raises ValueError on any problem."""
        if not isinstance(record, Mapping):
            raise ValueError("word must be an object")
        if set(record) != set(_WORD_FIELDS):
            raise ValueError(f"word must have exactly the keys {', '.join(_WORD_FIELDS)}")
        return cls(record["text"], record["start_ms"], record["end_ms"], record["confidence"])


@dataclass(frozen=True, slots=True)
class Turn:
    """One diarization turn: `speaker_label` (the diarizer's anonymous cluster id) spoke during [start_ms, end_ms)."""

    speaker_label: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.speaker_label, str) or not self.speaker_label.strip():
            raise ValueError(f"turn speaker_label must be a non-blank string: {self!r}")
        if not (_is_int(self.start_ms) and _is_int(self.end_ms)):
            raise ValueError(f"turn times must be whole milliseconds (int): {self!r}")
        if not 0 <= self.start_ms < self.end_ms:
            raise ValueError(f"turn times must satisfy 0 <= start_ms < end_ms: {self!r}")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @classmethod
    def from_record(cls, record: object) -> Turn:
        if not isinstance(record, Mapping):
            raise ValueError("turn must be an object")
        if set(record) != set(_TURN_FIELDS):
            raise ValueError(f"turn must have exactly the keys {', '.join(_TURN_FIELDS)}")
        return cls(record["speaker_label"], record["start_ms"], record["end_ms"])


def _turn_order(turn: Turn) -> tuple[int, int, str]:
    return (turn.start_ms, turn.end_ms, turn.speaker_label)


def assign_words_to_turns(words: Sequence[Word], turns: Sequence[Turn]) -> list[Turn]:
    """The turn each word belongs to, in the order of `words`. See the module docstring for the rules.

    Raises ValueError when there are words but no turns: who said them is unknown, and guessing would be silent.
    """
    if not words:
        return []
    if not turns:
        raise ValueError("cannot assign words to speakers: diarization produced no turns")
    ordered = sorted(turns, key=_turn_order)
    starts = [turn.start_ms for turn in ordered]
    # latest_end[i]: index of the turn with the latest end among ordered[: i + 1] (the first such on ties).
    latest_end: list[int] = []
    best = 0
    for index, turn in enumerate(ordered):
        if turn.end_ms > ordered[best].end_ms:
            best = index
        latest_end.append(best)

    assigned = []
    for word in words:
        start, end = word.start_ms, max(word.end_ms, word.start_ms + 1)
        before_end = bisect_left(starts, end)  # ordered[:before_end] start before the word ends
        chosen: Turn | None = None
        chosen_overlap = 0
        index = before_end - 1
        # Walk back while some earlier turn still ends after the word starts; nothing further back can overlap.
        while index >= 0 and ordered[latest_end[index]].end_ms > start:
            turn = ordered[index]
            overlap = min(end, turn.end_ms) - max(start, turn.start_ms)
            if overlap > 0 and overlap >= chosen_overlap:  # walking backwards, >= keeps the earlier turn on ties
                chosen, chosen_overlap = turn, overlap
            index -= 1
        if chosen is None:
            # No overlap: every turn before `before_end` ends at or before the word starts, every later one starts
            # at or after it ends. The nearest are the latest-ending earlier turn and the first later turn.
            previous = ordered[latest_end[before_end - 1]] if before_end > 0 else None
            following = ordered[before_end] if before_end < len(ordered) else None
            if previous is not None and (following is None or start - previous.end_ms <= following.start_ms - end):
                chosen = previous
            else:
                chosen = following
        if chosen is None:  # unreachable: turns is not empty
            raise AssertionError("no turn chosen")
        assigned.append(chosen)
    return assigned
