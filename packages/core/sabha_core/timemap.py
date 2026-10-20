"""Time mapping between compact (speech-only) audio and the original recording timeline.

Golden rule 4: silence is indexed, not deleted. Preprocessing keeps only speech in compact.wav and writes a
segment map, segments@v1.json, saying where each piece of compact audio came from. Diarization and ASR run on
compact audio; every timestamp shown to a user is first mapped back to the ORIGINAL timeline.

Semantics (all times are integer milliseconds; all intervals are half-open, [start, end)):

- A segment covers [orig_start_ms, orig_end_ms) of the original recording and the same length of compact audio
  from compact_start_ms. Segments are in original-time order and do not overlap (a hand-built map may have
  touching segments). They are packed end to end in compact time: the first starts at 0 and each next one starts
  where the previous one ends. compact_length_ms is the total speech.
- `compact_to_original(c)` accepts 0 <= c <= compact_length_ms and raises ValueError otherwise. A compact time at
  the join between two segments belongs to the later segment. The compact end (c == compact_length_ms) maps to
  the last segment's orig_end_ms.
- `original_to_compact(o)` accepts o >= 0 and raises ValueError for negative times. Inside speech it is exact.
  A time in silence (before the first segment, between segments, or exactly at a segment's end) maps to the join
  where that silence was cut out, which is the next segment's compact_start_ms. A time at or after the last
  segment's end maps to compact_length_ms. segments@v1.json does not record the recording's length, so times past
  the end of the recording are not rejected here; check them against `stats(...)["total_ms"]` where it matters.
- Round trips: compact -> original -> compact is exact for every compact time. original -> compact -> original is
  exact for every time inside speech; a time in silence snaps forward to the start of the next segment, or back
  to the end of the last segment when no speech follows.
- A map with no speech has compact_length_ms 0: compact time 0 maps to original 0, and every original time maps
  to compact 0.
"""

from __future__ import annotations

import json
import operator
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TypedDict, TypeGuard

DEFAULT_END_PAD_MS = 300
"""Padding added to the end of each VAD speech region (P3.3). An unmeasured starting value: tune it on the gold set."""

DEFAULT_MERGE_GAP_MS = 1500
"""Speech regions separated by less silence than this are merged into one segment (P3.3)."""

_FIELDS = ("orig_start_ms", "orig_end_ms", "compact_start_ms")


class SegmentRecord(TypedDict):
    """One entry of segments@v1.json."""

    orig_start_ms: int
    orig_end_ms: int
    compact_start_ms: int


class SegmentStats(TypedDict):
    """Speech and silence totals for one recording. speech_ms + silence_ms == total_ms."""

    total_ms: int
    speech_ms: int
    silence_ms: int
    longest_silence_ms: int  # includes leading and trailing silence


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class Segment:
    """A piece of speech: original [orig_start_ms, orig_end_ms), placed in compact audio at compact_start_ms."""

    orig_start_ms: int
    orig_end_ms: int
    compact_start_ms: int

    def __post_init__(self) -> None:
        if not all(_is_int(getattr(self, name)) for name in _FIELDS):
            raise ValueError(f"segment times must be whole milliseconds (int): {self}")
        if self.orig_start_ms < 0 or self.compact_start_ms < 0:
            raise ValueError(f"segment times cannot be negative: {self}")
        if self.orig_start_ms >= self.orig_end_ms:
            raise ValueError(f"segment start must be before its end: {self}")

    @property
    def duration_ms(self) -> int:
        return self.orig_end_ms - self.orig_start_ms

    @property
    def compact_end_ms(self) -> int:
        return self.compact_start_ms + self.duration_ms


@dataclass(frozen=True, slots=True)
class SegmentMap:
    """The validated, ordered segments of one recording, with exact mappings in both directions."""

    segments: tuple[Segment, ...]
    # Search keys for bisect, derived from `segments`.
    _compact_starts: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _orig_starts: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        segments = tuple(self.segments)  # accept any iterable, but never keep a caller's mutable list
        for index, segment in enumerate(segments):
            if not isinstance(segment, Segment):
                raise ValueError(f"segment {index} is not a Segment")
            if index == 0:
                if segment.compact_start_ms != 0:
                    raise ValueError(f"the first segment must have compact_start_ms 0, not {segment.compact_start_ms}")
                continue
            previous = segments[index - 1]
            if segment.orig_start_ms < previous.orig_start_ms:
                raise ValueError(f"segment {index} starts before segment {index - 1}: segments must be in order")
            if segment.orig_start_ms < previous.orig_end_ms:
                raise ValueError(f"segment {index} overlaps segment {index - 1} on the original timeline")
            if segment.compact_start_ms != previous.compact_end_ms:
                raise ValueError(
                    f"compact starts must be contiguous: segment {index} has compact_start_ms "
                    f"{segment.compact_start_ms}, expected {previous.compact_end_ms}"
                )
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "_compact_starts", tuple(s.compact_start_ms for s in segments))
        object.__setattr__(self, "_orig_starts", tuple(s.orig_start_ms for s in segments))

    @property
    def compact_length_ms(self) -> int:
        """Length of the compact audio, which is the total speech."""
        return self.segments[-1].compact_end_ms if self.segments else 0

    def compact_to_original(self, compact_ms: int) -> int:
        """Map a compact time to the original timeline. See the module docstring for the exact rules."""
        compact_ms = operator.index(compact_ms)
        if not 0 <= compact_ms <= self.compact_length_ms:
            raise ValueError(f"compact time {compact_ms} ms is outside the compact audio [0, {self.compact_length_ms}]")
        if not self.segments:
            return 0
        # bisect_right puts a join in the later segment; the compact end falls in the last segment's range.
        segment = self.segments[bisect_right(self._compact_starts, compact_ms) - 1]
        return segment.orig_start_ms + (compact_ms - segment.compact_start_ms)

    def original_to_compact(self, original_ms: int) -> int:
        """Map an original time to compact audio. Silence maps to the join where it was cut out."""
        original_ms = operator.index(original_ms)
        if original_ms < 0:
            raise ValueError(f"original time {original_ms} ms is negative")
        index = bisect_right(self._orig_starts, original_ms) - 1
        if index < 0:
            return 0  # leading silence, or no speech at all
        segment = self.segments[index]
        if original_ms < segment.orig_end_ms:
            return segment.compact_start_ms + (original_ms - segment.orig_start_ms)
        return segment.compact_end_ms  # silence after this segment: the next join, or the compact end

    def to_records(self) -> list[SegmentRecord]:
        """The segments@v1.json content: [{orig_start_ms, orig_end_ms, compact_start_ms}, ...]."""
        return [
            {"orig_start_ms": s.orig_start_ms, "orig_end_ms": s.orig_end_ms, "compact_start_ms": s.compact_start_ms}
            for s in self.segments
        ]

    def to_json(self) -> str:
        return json.dumps(self.to_records())

    @classmethod
    def from_records(cls, records: Iterable[object]) -> SegmentMap:
        """Build and validate a map from segments@v1.json content. Raises ValueError on any problem."""
        segments = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ValueError(f"segment {index} must be an object")
            if set(record) != set(_FIELDS):
                raise ValueError(f"segment {index} must have exactly the keys {', '.join(_FIELDS)}")
            orig_start, orig_end, compact_start = (record[name] for name in _FIELDS)
            if not (_is_int(orig_start) and _is_int(orig_end) and _is_int(compact_start)):
                raise ValueError(f"segment {index} times must be whole milliseconds (int)")
            segments.append(Segment(orig_start, orig_end, compact_start))
        return cls(tuple(segments))

    @classmethod
    def from_json(cls, text: str | bytes) -> SegmentMap:
        try:
            data = json.loads(text)
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
            raise ValueError(f"segment map is not valid JSON: {exc}") from None
        if not isinstance(data, list):
            raise ValueError("segment map JSON must be a list of segments")
        return cls.from_records(data)


def build_segment_map(
    speech_regions_ms: Iterable[tuple[int, int]],
    total_ms: int,
    end_pad_ms: int = DEFAULT_END_PAD_MS,
    merge_gap_ms: int = DEFAULT_MERGE_GAP_MS,
) -> SegmentMap:
    """Turn raw VAD speech regions [(start_ms, end_ms), ...] into a segment map.

    Each region gets `end_pad_ms` added to its end and is clamped to [0, total_ms]; a region left empty by clamping
    (VAD and ffprobe can disagree by a few ms at the end) is dropped. Regions are sorted, then neighbours are
    merged when the silence between them is shorter than `merge_gap_ms`; regions that overlap or touch after
    padding are always merged. Compact starts are assigned in order from 0. No regions gives an empty map.
    """
    total_ms, end_pad_ms, merge_gap_ms = (operator.index(value) for value in (total_ms, end_pad_ms, merge_gap_ms))
    for name, value in (("total_ms", total_ms), ("end_pad_ms", end_pad_ms), ("merge_gap_ms", merge_gap_ms)):
        if value < 0:
            raise ValueError(f"{name} cannot be negative, got {value}")

    regions = []
    for raw_start, raw_end in speech_regions_ms:
        start, end = operator.index(raw_start), operator.index(raw_end)
        if start >= end:
            raise ValueError(f"speech region must have start < end, got ({start}, {end})")
        start, end = max(start, 0), min(end + end_pad_ms, total_ms)
        if start < end:
            regions.append((start, end))
    regions.sort()

    merged: list[tuple[int, int]] = []
    for start, end in regions:
        # A gap of 0 or less is no silence at all, so touching and overlapping regions merge even if merge_gap_ms is 0.
        if merged and start - merged[-1][1] < max(merge_gap_ms, 1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    segments = []
    compact_ms = 0
    for start, end in merged:
        segments.append(Segment(start, end, compact_ms))
        compact_ms += end - start
    return SegmentMap(tuple(segments))


def stats(segment_map: SegmentMap, total_ms: int) -> SegmentStats:
    """Speech and silence totals; silence includes any before the first segment and after the last."""
    total_ms = operator.index(total_ms)
    speech_end_ms = segment_map.segments[-1].orig_end_ms if segment_map.segments else 0
    if total_ms < speech_end_ms:
        raise ValueError(f"total_ms {total_ms} is shorter than the speech, which ends at {speech_end_ms} ms")
    silences = []
    cursor_ms = 0
    for segment in segment_map.segments:
        silences.append(segment.orig_start_ms - cursor_ms)
        cursor_ms = segment.orig_end_ms
    silences.append(total_ms - cursor_ms)
    speech_ms = segment_map.compact_length_ms
    return {
        "total_ms": total_ms,
        "speech_ms": speech_ms,
        "silence_ms": total_ms - speech_ms,
        "longest_silence_ms": max(silences),
    }
