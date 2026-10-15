"""Tests for sabha_asr.chunking: planning ASR chunks over compact audio and merging their words (P3.5).

The ASR is simulated: for each chunk it returns, chunk-relative, every word that lies wholly inside the chunk's
audio, and a garbled fragment (text ending in "~") for every word the chunk's edge cuts. A correct plan and merge
give back exactly the original words: each once, whole, and never a fragment.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sabha_asr.chunking import (
    DEFAULT_MAX_CHUNK_MS,
    DEFAULT_OVERLAP_MS,
    Chunk,
    compact_joins,
    merge_chunk_words,
    plan_chunks,
)
from sabha_asr.words import Word
from sabha_core.timemap import Segment, SegmentMap


def fake_asr(chunk: Chunk, truth: list[Word]) -> list[Word]:
    """What an ASR would return for this chunk's audio, in chunk-relative time."""
    out = []
    for w in truth:
        if chunk.start_ms <= w.start_ms and w.end_ms <= chunk.end_ms:
            out.append(w.shifted(-chunk.start_ms))
        elif w.start_ms < chunk.end_ms and w.end_ms > chunk.start_ms:  # cut by the chunk edge
            start, end = max(w.start_ms, chunk.start_ms), min(w.end_ms, chunk.end_ms)
            out.append(Word(w.text + "~", start - chunk.start_ms, end - chunk.start_ms, 0.3))
    return out


def run(chunks: tuple[Chunk, ...], truth: list[Word]) -> list[Word]:
    return merge_chunk_words((chunk, fake_asr(chunk, truth)) for chunk in chunks)


def assert_tiles(chunks: tuple[Chunk, ...], length_ms: int) -> None:
    """Owned regions cover [0, length) exactly, in order, with no gaps or overlaps."""
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].owned_start_ms == 0
    assert chunks[-1].owned_end_ms == length_ms
    for before, after in pairwise(chunks):
        assert before.owned_end_ms == after.owned_start_ms


# --- compact_joins ---------------------------------------------------------------------------------------------


def test_compact_joins_are_the_places_where_silence_was_cut() -> None:
    segment_map = SegmentMap(
        (
            Segment(1000, 3000, 0),
            Segment(5000, 6000, 2000),
            Segment(6000, 6500, 3000),  # touches the previous segment: no silence removed, not a join
            Segment(8000, 9000, 3500),
        )
    )
    assert compact_joins(segment_map) == (2000, 3500)
    assert compact_joins(SegmentMap(())) == ()


# --- plan_chunks -----------------------------------------------------------------------------------------------


def test_defaults_are_the_plan_values() -> None:
    assert (DEFAULT_MAX_CHUNK_MS, DEFAULT_OVERLAP_MS) == (30_000, 500)


def test_empty_audio_has_no_chunks() -> None:
    assert plan_chunks(0, ()) == ()


def test_short_pieces_are_packed_and_cut_only_at_joins() -> None:
    # Pieces of 10 s, 10 s, 15 s, 5 s between joins: [0, 20 s) fits, adding 15 s would exceed 30 s.
    chunks = plan_chunks(40_000, (10_000, 20_000, 35_000))
    assert [(c.start_ms, c.end_ms) for c in chunks] == [(0, 20_000), (20_000, 40_000)]
    for c in chunks:
        assert (c.owned_start_ms, c.owned_end_ms) == (c.start_ms, c.end_ms)  # no overlap at VAD joins
    assert_tiles(chunks, 40_000)


def test_join_order_duplicates_and_ends_do_not_matter() -> None:
    assert plan_chunks(40_000, (35_000, 0, 10_000, 20_000, 20_000, 40_000)) == plan_chunks(
        40_000, (10_000, 20_000, 35_000)
    )


def test_join_outside_audio_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside"):
        plan_chunks(10_000, (12_000,))
    with pytest.raises(ValueError, match="outside"):
        plan_chunks(10_000, (-1,))


@pytest.mark.parametrize(
    ("max_chunk_ms", "overlap_ms"),
    [(1000, 501), (1000, 600), (0, 0), (30_000, -2), (30_000, 499)],
)
def test_bad_parameters_are_rejected(max_chunk_ms: int, overlap_ms: int) -> None:
    with pytest.raises(ValueError):
        plan_chunks(60_000, (), max_chunk_ms=max_chunk_ms, overlap_ms=overlap_ms)


def test_long_segment_is_split_with_exact_overlap() -> None:
    # One 70 s segment (a lesson with no long pause): no join to cut at, so it is split with overlap.
    chunks = plan_chunks(70_000, ())
    assert len(chunks) == 3
    assert_tiles(chunks, 70_000)
    for c in chunks:
        assert c.duration_ms <= DEFAULT_MAX_CHUNK_MS
    for before, after in pairwise(chunks):
        assert before.end_ms - after.start_ms == DEFAULT_OVERLAP_MS  # audio overlap is exactly 0.5 s
        join = before.owned_end_ms
        assert (join - after.start_ms, before.end_ms - join) == (250, 250)  # centred on the owned boundary
    assert chunks[0].start_ms == 0 and chunks[-1].end_ms == 70_000  # no overlap past the audio


def test_long_segment_between_joins_does_not_overlap_into_neighbours() -> None:
    # 5 s, then a 50 s segment, then 5 s. Only the long segment is split; its outer edges stay at the joins.
    chunks = plan_chunks(60_000, (5_000, 55_000))
    assert_tiles(chunks, 60_000)
    assert chunks[0].end_ms == 5_000
    assert chunks[-1].start_ms == 55_000
    middle = chunks[1:-1]
    assert middle[0].start_ms == 5_000 and middle[-1].end_ms == 55_000
    for c in chunks:
        assert c.duration_ms <= DEFAULT_MAX_CHUNK_MS


def test_segment_exactly_max_long_is_not_split() -> None:
    chunks = plan_chunks(30_000, ())
    assert [(c.start_ms, c.end_ms, c.owned_start_ms, c.owned_end_ms) for c in chunks] == [(0, 30_000, 0, 30_000)]


@settings(max_examples=200, deadline=None)
@given(
    length=st.integers(min_value=1, max_value=400_000),
    raw_joins=st.lists(st.integers(min_value=0, max_value=400_000), max_size=20),
    max_chunk_ms=st.integers(min_value=1000, max_value=40_000),
    half_overlap=st.integers(min_value=0, max_value=500),
)
def test_plan_properties(length: int, raw_joins: list[int], max_chunk_ms: int, half_overlap: int) -> None:
    overlap_ms = 2 * min(half_overlap, max_chunk_ms // 4)  # the largest overlap plan_chunks accepts
    joins = [j for j in raw_joins if j <= length]
    chunks = plan_chunks(length, joins, max_chunk_ms=max_chunk_ms, overlap_ms=overlap_ms)
    assert_tiles(chunks, length)
    cut_points = {0, length, *joins}
    for c in chunks:
        assert c.duration_ms <= max_chunk_ms
        assert c.start_ms <= c.owned_start_ms < c.owned_end_ms <= c.end_ms
    for before, after in pairwise(chunks):
        boundary = before.owned_end_ms
        if boundary in cut_points:
            assert before.end_ms == boundary == after.start_ms  # VAD joins: no overlap
        else:
            assert before.end_ms - after.start_ms == overlap_ms
            # A forced split never reaches across a VAD join.
            assert not any(after.start_ms < j < before.end_ms for j in cut_points)


# --- merge_chunk_words -----------------------------------------------------------------------------------------


def test_word_straddling_a_split_appears_exactly_once_and_whole() -> None:
    chunks = plan_chunks(70_000, ())
    split = chunks[0].owned_end_ms
    truth = [
        Word("pehle", split - 1200, split - 800, 0.9),
        Word("straddle", split - 300, split + 100, 0.8),  # crosses the owned boundary
        Word("baad", split + 400, split + 700, 0.95),
    ]
    merged = run(chunks, truth)
    assert merged == truth
    assert not any(w.text.endswith("~") for w in merged)


def test_word_whose_midpoint_is_on_the_boundary_belongs_to_the_later_chunk() -> None:
    chunks = plan_chunks(70_000, ())
    split = chunks[0].owned_end_ms
    truth = [Word("beech", split - 200, split + 200, 0.9)]
    assert run(chunks, truth) == truth
    # Both chunks heard it whole; only the later one keeps it.
    assert merge_chunk_words([(chunks[0], fake_asr(chunks[0], truth)), (chunks[1], []), (chunks[2], [])]) == []


def test_words_are_returned_on_the_compact_timeline_in_order() -> None:
    chunks = plan_chunks(40_000, (10_000, 20_000, 35_000))
    truth = [Word("ek", 500, 900, 0.9), Word("do", 21_000, 21_400, 0.9), Word("teen", 39_000, 39_500, 0.9)]
    per_chunk = [(c, fake_asr(c, truth)) for c in chunks]
    assert per_chunk[1][1][0].start_ms == 1000  # chunk-relative going in
    assert merge_chunk_words(reversed(per_chunk)) == truth


def test_word_end_past_chunk_audio_is_clamped() -> None:
    (chunk,) = plan_chunks(10_000, ())
    merged = merge_chunk_words([(chunk, [Word("ant", 9_800, 10_050, 0.9)])])
    assert merged == [Word("ant", 9_800, 10_000, 0.9)]


def test_word_starting_after_chunk_audio_is_rejected() -> None:
    (chunk,) = plan_chunks(10_000, ())
    with pytest.raises(ValueError, match="outside"):
        merge_chunk_words([(chunk, [Word("ghost", 10_001, 10_100, 0.9)])])


def test_missing_chunk_is_an_error_not_a_silent_gap() -> None:
    chunks = plan_chunks(70_000, ())
    with pytest.raises(ValueError, match="cover"):
        merge_chunk_words([(chunks[0], []), (chunks[2], [])])
    with pytest.raises(ValueError, match="cover"):
        merge_chunk_words([(chunks[0], []), (chunks[0], []), (chunks[1], []), (chunks[2], [])])


def test_merge_of_nothing_is_empty() -> None:
    assert merge_chunk_words([]) == []


def test_zero_length_word_at_the_very_end_is_kept() -> None:
    (chunk,) = plan_chunks(10_000, ())
    assert merge_chunk_words([(chunk, [Word("end", 10_000, 10_000, 0.9)])]) == [Word("end", 10_000, 10_000, 0.9)]


@st.composite
def audio_with_words(draw: st.DrawFn) -> tuple[int, list[int], list[Word]]:
    """Compact audio with non-overlapping words no longer than the overlap, inside VAD pieces (never across a join)."""
    pieces = draw(st.lists(st.integers(min_value=1_000, max_value=90_000), min_size=1, max_size=5))
    joins: list[int] = []
    words: list[Word] = []
    cursor = 0
    gap = st.integers(min_value=0, max_value=3_000)
    length = st.integers(min_value=0, max_value=DEFAULT_OVERLAP_MS)
    for piece in pieces:
        t = cursor
        for gap_ms, length_ms in draw(st.lists(st.tuples(gap, length), max_size=60)):
            t += gap_ms
            if t + length_ms > cursor + piece:
                break
            words.append(Word(f"w{len(words)}", t, t + length_ms, 0.9))
            t += length_ms
        cursor += piece
        joins.append(cursor)
    return cursor, joins[:-1], words


@settings(max_examples=150, deadline=None)
@given(audio_with_words())
def test_every_word_comes_back_exactly_once_and_is_never_split(audio: tuple[int, list[int], list[Word]]) -> None:
    length, joins, truth = audio
    chunks = plan_chunks(length, joins)
    for w in truth:
        # The chunk that owns the word's midpoint hears the whole word.
        owner = [c for c in chunks if c.owned_start_ms * 2 <= w.start_ms + w.end_ms < c.owned_end_ms * 2]
        if w.start_ms + w.end_ms == 2 * length:
            owner = [chunks[-1]]
        assert len(owner) == 1
        assert owner[0].start_ms <= w.start_ms and w.end_ms <= owner[0].end_ms
    assert run(chunks, truth) == truth
