"""Tests for sabha_core.timemap: mapping between compact (speech-only) audio and the original recording.

Golden rule 4: silence is indexed, not deleted, and every timestamp shown to a user is on the original timeline.
A mapping that is off by even one millisecond moves a quote away from its audio, so these tests are exact.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sabha_core.timemap import Segment, SegmentMap, build_segment_map, stats

# Speech at [1000, 3000), [5000, 6000), [6000, 6500) and [8000, 9000) of a 10 s recording. The second and third
# segments touch (no silence between them), which a hand-built map may do.
EXAMPLE = SegmentMap(
    (
        Segment(orig_start_ms=1000, orig_end_ms=3000, compact_start_ms=0),
        Segment(orig_start_ms=5000, orig_end_ms=6000, compact_start_ms=2000),
        Segment(orig_start_ms=6000, orig_end_ms=6500, compact_start_ms=3000),
        Segment(orig_start_ms=8000, orig_end_ms=9000, compact_start_ms=3500),
    )
)
EXAMPLE_TOTAL_MS = 10_000

EMPTY = SegmentMap(())


def spans(segment_map: SegmentMap) -> list[tuple[int, int, int]]:
    return [(s.orig_start_ms, s.orig_end_ms, s.compact_start_ms) for s in segment_map.segments]


# --- compact -> original -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("compact_ms", "original_ms"),
    [
        (0, 1000),  # start of compact audio is the start of the first segment
        (1, 1001),
        (1999, 2999),  # last ms of the first segment
        (2000, 5000),  # a join belongs to the later segment
        (2999, 5999),
        (3000, 6000),  # join between touching segments
        (3499, 6499),
        (3500, 8000),
        (4499, 8999),
        (4500, 9000),  # the compact end maps to the last segment's original end
    ],
)
def test_compact_to_original_at_boundaries(compact_ms: int, original_ms: int) -> None:
    assert EXAMPLE.compact_to_original(compact_ms) == original_ms


@pytest.mark.parametrize("compact_ms", [-1, 4501, 10_000])
def test_compact_time_outside_the_compact_audio_is_rejected(compact_ms: int) -> None:
    with pytest.raises(ValueError, match="compact"):
        EXAMPLE.compact_to_original(compact_ms)


def test_compact_length_is_the_total_speech() -> None:
    assert EXAMPLE.compact_length_ms == 4500
    assert EMPTY.compact_length_ms == 0


# --- original -> compact -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("original_ms", "compact_ms"),
    [
        (0, 0),  # leading silence maps to the join before the first segment
        (999, 0),
        (1000, 0),
        (1001, 1),
        (2999, 1999),
        (3000, 2000),  # a segment's end is not inside it (half-open), so it is silence: the next join
        (4000, 2000),
        (4999, 2000),
        (5000, 2000),
        (5999, 2999),
        (6000, 3000),  # touching segments
        (6499, 3499),
        (6500, 3500),
        (7999, 3500),
        (8000, 3500),
        (8999, 4499),
        (9000, 4500),  # after the last segment: the compact end
        (9999, 4500),
        (10**9, 4500),
    ],
)
def test_original_to_compact_at_boundaries_and_in_silence(original_ms: int, compact_ms: int) -> None:
    assert EXAMPLE.original_to_compact(original_ms) == compact_ms


def test_negative_original_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="original"):
        EXAMPLE.original_to_compact(-1)


def test_silence_snaps_forward_to_the_next_speech_on_a_round_trip() -> None:
    assert EXAMPLE.compact_to_original(EXAMPLE.original_to_compact(500)) == 1000
    assert EXAMPLE.compact_to_original(EXAMPLE.original_to_compact(4000)) == 5000
    # After the last segment there is no next speech: the compact end maps back to the last segment's end.
    assert EXAMPLE.compact_to_original(EXAMPLE.original_to_compact(9500)) == 9000


def test_round_trips_are_exact_for_every_ms_of_the_example() -> None:
    for compact_ms in range(EXAMPLE.compact_length_ms + 1):
        assert EXAMPLE.original_to_compact(EXAMPLE.compact_to_original(compact_ms)) == compact_ms
    for segment in EXAMPLE.segments:
        for original_ms in range(segment.orig_start_ms, segment.orig_end_ms):
            assert EXAMPLE.compact_to_original(EXAMPLE.original_to_compact(original_ms)) == original_ms


def test_empty_map_has_no_speech() -> None:
    assert EMPTY.compact_to_original(0) == 0
    assert EMPTY.original_to_compact(0) == 0
    assert EMPTY.original_to_compact(5000) == 0
    with pytest.raises(ValueError, match="compact"):
        EMPTY.compact_to_original(1)


# --- validation ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("orig_start_ms", "orig_end_ms", "compact_start_ms", "problem"),
    [
        (1000, 1000, 0, "start"),
        (2000, 1000, 0, "start"),
        (-1, 1000, 0, "negative"),
        (0, 1000, -1, "negative"),
    ],
)
def test_invalid_segment_is_rejected(orig_start_ms: int, orig_end_ms: int, compact_start_ms: int, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        Segment(orig_start_ms=orig_start_ms, orig_end_ms=orig_end_ms, compact_start_ms=compact_start_ms)


@pytest.mark.parametrize(
    ("segments", "problem"),
    [
        ([(1000, 2000, 5)], "first segment"),
        ([(1000, 2000, 0), (3000, 4000, 999)], "contiguous"),
        ([(1000, 2000, 0), (3000, 4000, 1001)], "contiguous"),
        ([(3000, 4000, 0), (1000, 2000, 1000)], "order"),
        ([(1000, 2000, 0), (1500, 2500, 1000)], "overlap"),
        ([(1000, 2000, 0), (1000, 2000, 1000)], "overlap"),
    ],
)
def test_invalid_segment_map_is_rejected(segments: list[tuple[int, int, int]], problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        SegmentMap(tuple(Segment(*values) for values in segments))


def test_segment_map_is_immutable() -> None:
    with pytest.raises(AttributeError):
        EXAMPLE.segments = ()  # type: ignore[misc]  # deliberately assigning to a frozen dataclass field


# --- JSON (segments@v1.json) ---------------------------------------------------------------------------------


def test_json_has_the_segments_v1_shape() -> None:
    assert json.loads(EXAMPLE.to_json()) == [
        {"orig_start_ms": 1000, "orig_end_ms": 3000, "compact_start_ms": 0},
        {"orig_start_ms": 5000, "orig_end_ms": 6000, "compact_start_ms": 2000},
        {"orig_start_ms": 6000, "orig_end_ms": 6500, "compact_start_ms": 3000},
        {"orig_start_ms": 8000, "orig_end_ms": 9000, "compact_start_ms": 3500},
    ]
    assert EXAMPLE.to_records() == json.loads(EXAMPLE.to_json())


def test_json_round_trip() -> None:
    assert SegmentMap.from_json(EXAMPLE.to_json()) == EXAMPLE
    assert SegmentMap.from_json(EXAMPLE.to_json().encode()) == EXAMPLE
    assert SegmentMap.from_records(EXAMPLE.to_records()) == EXAMPLE
    assert SegmentMap.from_json(EMPTY.to_json()) == EMPTY
    assert EMPTY.to_json() == "[]"


@pytest.mark.parametrize(
    "text",
    [
        '{"orig_start_ms": 0, "orig_end_ms": 10, "compact_start_ms": 0}',  # not a list
        "[[0, 10, 0]]",  # not an object
        '[{"orig_start_ms": 0, "orig_end_ms": 10}]',  # missing key
        '[{"orig_start_ms": 0, "orig_end_ms": 10, "compact_start_ms": 0, "extra": 1}]',  # unknown key
        '[{"orig_start_ms": 0.0, "orig_end_ms": 10, "compact_start_ms": 0}]',  # float
        '[{"orig_start_ms": "0", "orig_end_ms": 10, "compact_start_ms": 0}]',  # string
        '[{"orig_start_ms": false, "orig_end_ms": 10, "compact_start_ms": 0}]',  # bool
        '[{"orig_start_ms": 0, "orig_end_ms": 10, "compact_start_ms": 3}]',  # valid shape, invalid map
        "not json",
    ],
)
def test_malformed_json_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        SegmentMap.from_json(text)


# --- build_segment_map ---------------------------------------------------------------------------------------


def test_no_speech_builds_an_empty_map() -> None:
    assert build_segment_map([], total_ms=60_000) == EMPTY


def test_defaults_pad_300_ms_and_merge_gaps_under_1500_ms() -> None:
    segment_map = build_segment_map([(1000, 2000), (3000, 4000), (10_000, 11_000)], total_ms=60_000)

    # [1000, 2300) and [3000, 4300) are 700 ms apart and merge; [10000, 11300) is 5700 ms away and stays separate.
    assert spans(segment_map) == [(1000, 4300, 0), (10_000, 11_300, 3300)]


def test_end_padding_is_added_to_each_region() -> None:
    segment_map = build_segment_map([(1000, 2000), (5000, 6000)], total_ms=60_000, end_pad_ms=300, merge_gap_ms=0)

    assert spans(segment_map) == [(1000, 2300, 0), (5000, 6300, 1300)]


def test_gap_of_exactly_merge_gap_is_kept() -> None:
    # Padded first region ends at 2300; the next starts 1500 ms later.
    segment_map = build_segment_map([(1000, 2000), (3800, 4000)], total_ms=60_000)

    assert spans(segment_map) == [(1000, 2300, 0), (3800, 4300, 1300)]


def test_gap_just_under_merge_gap_is_merged() -> None:
    segment_map = build_segment_map([(1000, 2000), (3799, 4000)], total_ms=60_000)

    assert spans(segment_map) == [(1000, 4300, 0)]


def test_overlap_created_by_padding_is_merged_even_without_a_merge_gap() -> None:
    segment_map = build_segment_map([(1000, 2000), (2100, 3000)], total_ms=60_000, end_pad_ms=300, merge_gap_ms=0)

    assert spans(segment_map) == [(1000, 3300, 0)]


def test_touching_regions_are_merged_even_without_a_merge_gap() -> None:
    segment_map = build_segment_map([(1000, 2000), (2300, 3000)], total_ms=60_000, end_pad_ms=300, merge_gap_ms=0)

    assert spans(segment_map) == [(1000, 3300, 0)]


def test_region_inside_another_is_absorbed() -> None:
    segment_map = build_segment_map([(1000, 5000), (2000, 3000)], total_ms=60_000)

    assert spans(segment_map) == [(1000, 5300, 0)]


def test_regions_are_sorted_first() -> None:
    segment_map = build_segment_map([(5000, 6000), (1000, 2000)], total_ms=60_000, end_pad_ms=0, merge_gap_ms=0)

    assert spans(segment_map) == [(1000, 2000, 0), (5000, 6000, 1000)]


def test_padding_is_clamped_at_the_end_of_the_recording() -> None:
    segment_map = build_segment_map([(9800, 9900)], total_ms=10_000)

    assert spans(segment_map) == [(9800, 10_000, 0)]


def test_region_past_the_end_is_clamped_or_dropped() -> None:
    # VAD and ffprobe can disagree by a few ms at the end; such regions are clamped, and dropped if nothing is left.
    assert spans(build_segment_map([(9800, 10_500)], total_ms=10_000)) == [(9800, 10_000, 0)]
    assert build_segment_map([(10_000, 10_100)], total_ms=10_000) == EMPTY


def test_negative_start_is_clamped_to_zero() -> None:
    assert spans(build_segment_map([(-200, 500)], total_ms=10_000)) == [(0, 800, 0)]


@pytest.mark.parametrize(
    ("regions", "total_ms", "end_pad_ms", "merge_gap_ms", "problem"),
    [
        ([(1000, 1000)], 10_000, 300, 1500, "speech region"),
        ([(2000, 1000)], 10_000, 300, 1500, "speech region"),
        ([], -1, 300, 1500, "total_ms"),
        ([], 10_000, -1, 1500, "end_pad_ms"),
        ([], 10_000, 300, -1, "merge_gap_ms"),
    ],
)
def test_invalid_build_arguments_are_rejected(
    regions: list[tuple[int, int]], total_ms: int, end_pad_ms: int, merge_gap_ms: int, problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        build_segment_map(regions, total_ms=total_ms, end_pad_ms=end_pad_ms, merge_gap_ms=merge_gap_ms)


# --- stats ---------------------------------------------------------------------------------------------------


def test_stats_of_the_example() -> None:
    # Silences: 1000 leading, 2000, 0, 1500 between segments, 1000 trailing.
    assert stats(EXAMPLE, EXAMPLE_TOTAL_MS) == {
        "total_ms": 10_000,
        "speech_ms": 4500,
        "silence_ms": 5500,
        "longest_silence_ms": 2000,
    }


def test_leading_and_trailing_silence_count() -> None:
    late_start = SegmentMap((Segment(5000, 6000, 0),))
    assert stats(late_start, 7000)["longest_silence_ms"] == 5000

    early_end = SegmentMap((Segment(0, 1000, 0),))
    assert stats(early_end, 7000) == {
        "total_ms": 7000,
        "speech_ms": 1000,
        "silence_ms": 6000,
        "longest_silence_ms": 6000,
    }


def test_stats_with_no_speech() -> None:
    assert stats(EMPTY, 5000) == {"total_ms": 5000, "speech_ms": 0, "silence_ms": 5000, "longest_silence_ms": 5000}
    assert stats(EMPTY, 0) == {"total_ms": 0, "speech_ms": 0, "silence_ms": 0, "longest_silence_ms": 0}


def test_stats_reject_a_total_shorter_than_the_speech() -> None:
    with pytest.raises(ValueError, match="total_ms"):
        stats(EXAMPLE, 8999)


# --- property tests ------------------------------------------------------------------------------------------


@st.composite
def maps_with_totals(draw: st.DrawFn) -> tuple[SegmentMap, int]:
    """A random valid segment map (touching segments allowed) and a recording length that contains it."""
    segments: list[Segment] = []
    orig_ms = draw(st.integers(0, 500))
    compact_ms = 0
    for _ in range(draw(st.integers(0, 8))):
        duration = draw(st.integers(1, 400))
        segments.append(Segment(orig_ms, orig_ms + duration, compact_ms))
        compact_ms += duration
        orig_ms += duration + draw(st.integers(0, 600))
    segment_map = SegmentMap(tuple(segments))
    last_end = segments[-1].orig_end_ms if segments else 0
    return segment_map, last_end + draw(st.integers(0, 500))


def reference_compact_to_original(segment_map: SegmentMap, compact_ms: int) -> int:
    """Linear-scan version of the documented rule, to check the binary search against."""
    for segment in segment_map.segments:
        duration = segment.orig_end_ms - segment.orig_start_ms
        if segment.compact_start_ms <= compact_ms < segment.compact_start_ms + duration:
            return segment.orig_start_ms + compact_ms - segment.compact_start_ms
    return segment_map.segments[-1].orig_end_ms if segment_map.segments else 0


def reference_original_to_compact(segment_map: SegmentMap, original_ms: int) -> int:
    for segment in segment_map.segments:
        if original_ms < segment.orig_start_ms:
            return segment.compact_start_ms  # in the silence before this segment
        if original_ms < segment.orig_end_ms:
            return segment.compact_start_ms + original_ms - segment.orig_start_ms
    return segment_map.compact_length_ms


@given(maps_with_totals())
def test_compact_round_trip_is_exact_for_every_ms(case: tuple[SegmentMap, int]) -> None:
    segment_map, _ = case
    previous = -1
    for compact_ms in range(segment_map.compact_length_ms + 1):
        original_ms = segment_map.compact_to_original(compact_ms)
        assert original_ms == reference_compact_to_original(segment_map, compact_ms)
        assert original_ms > previous  # strictly increasing: no two compact times share an original time
        assert segment_map.original_to_compact(original_ms) == compact_ms
        previous = original_ms


@given(maps_with_totals())
def test_original_round_trip_is_exact_inside_speech(case: tuple[SegmentMap, int]) -> None:
    segment_map, _ = case
    for segment in segment_map.segments:
        for original_ms in range(segment.orig_start_ms, segment.orig_end_ms):
            assert segment_map.compact_to_original(segment_map.original_to_compact(original_ms)) == original_ms


@given(maps_with_totals())
def test_original_to_compact_matches_the_rule_for_every_ms(case: tuple[SegmentMap, int]) -> None:
    segment_map, total_ms = case
    previous = 0
    for original_ms in range(total_ms + 1):
        compact_ms = segment_map.original_to_compact(original_ms)
        assert compact_ms == reference_original_to_compact(segment_map, original_ms)
        assert previous <= compact_ms <= segment_map.compact_length_ms
        previous = compact_ms


@given(maps_with_totals())
def test_json_round_trip_of_random_maps(case: tuple[SegmentMap, int]) -> None:
    segment_map, _ = case
    assert SegmentMap.from_json(segment_map.to_json()) == segment_map


@given(maps_with_totals())
def test_stats_add_up(case: tuple[SegmentMap, int]) -> None:
    segment_map, total_ms = case
    result = stats(segment_map, total_ms)

    speech = [False] * total_ms
    for segment in segment_map.segments:
        for ms in range(segment.orig_start_ms, segment.orig_end_ms):
            speech[ms] = True
    assert result["total_ms"] == total_ms
    assert result["speech_ms"] == sum(speech) == segment_map.compact_length_ms
    assert result["speech_ms"] + result["silence_ms"] == total_ms
    assert result["longest_silence_ms"] == max(run_lengths(speech, value=False), default=0)


def run_lengths(mask: list[bool], *, value: bool) -> list[int]:
    return [end - start for start, end in runs(mask, value=value)]


def runs(mask: list[bool], *, value: bool) -> list[tuple[int, int]]:
    """Half-open [start, end) runs of `value` in `mask`."""
    found: list[tuple[int, int]] = []
    start: int | None = None
    for ms, item in enumerate([*mask, not value]):
        if item == value and start is None:
            start = ms
        elif item != value and start is not None:
            found.append((start, ms))
            start = None
    return found


def reference_build(
    regions: list[tuple[int, int]], total_ms: int, end_pad_ms: int, merge_gap_ms: int
) -> list[tuple[int, int]]:
    """Millisecond-mask version of the documented build rule: pad, clamp, union, then fill short silences."""
    speech = [False] * total_ms
    for start, end in regions:
        for ms in range(max(start, 0), min(end + end_pad_ms, total_ms)):
            speech[ms] = True
    merged: list[tuple[int, int]] = []
    for start, end in runs(speech, value=True):
        if merged and start - merged[-1][1] < merge_gap_ms:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


@st.composite
def vad_cases(draw: st.DrawFn) -> tuple[list[tuple[int, int]], int, int, int]:
    total_ms = draw(st.integers(0, 4000))
    starts = st.integers(-200, total_ms + 200)
    regions = [(start, start + length) for start, length in draw(st.lists(st.tuples(starts, st.integers(1, 800))))]
    return regions, total_ms, draw(st.integers(0, 400)), draw(st.integers(0, 2000))


@given(vad_cases())
def test_build_matches_the_reference_rule(case: tuple[list[tuple[int, int]], int, int, int]) -> None:
    regions, total_ms, end_pad_ms, merge_gap_ms = case

    segment_map = build_segment_map(regions, total_ms=total_ms, end_pad_ms=end_pad_ms, merge_gap_ms=merge_gap_ms)

    expected = reference_build(regions, total_ms, end_pad_ms, merge_gap_ms)
    assert [(s.orig_start_ms, s.orig_end_ms) for s in segment_map.segments] == expected
    for before, after in zip(segment_map.segments, segment_map.segments[1:], strict=False):
        assert after.orig_start_ms - before.orig_end_ms >= max(merge_gap_ms, 1)
    result = stats(segment_map, total_ms)
    assert result["speech_ms"] + result["silence_ms"] == total_ms
