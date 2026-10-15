"""Planning ASR chunks over compact audio, and merging the words of the chunks back together (plan task P3.5).

ASR models take bounded audio (about 30 s for Whisper-style models), so compact.wav is cut into chunks. All times
here are integer milliseconds on the COMPACT timeline, and intervals are half-open, [start_ms, end_ms).

Planning (`plan_chunks`):

- The compact audio is first cut at VAD joins: the compact times where silence was removed (`compact_joins`).
  Nobody speaks across a removed silence, so cutting there cannot cut a word, and no overlap is needed.
- The pieces between joins are packed greedily, in order, into chunks of at most `max_chunk_ms`.
- A single piece longer than `max_chunk_ms` (a long stretch of talk with no pause long enough to be removed) must
  be split inside speech. Words are unknown before ASR, so no split point can be chosen to avoid them; overlap is
  the protection instead. The piece is divided into the fewest equal "owned" regions that fit, and each chunk's
  audio extends `overlap_ms / 2` past every split it borders, so neighbouring chunks share exactly `overlap_ms` of
  audio centred on the split. Overlap never reaches past a VAD join.
- Every chunk OWNS [owned_start_ms, owned_end_ms). Owned regions tile the compact audio with no gaps or overlaps.
  At VAD joins a chunk's audio and owned region are the same.

Merging (`merge_chunk_words`), the owned-region rule:

- Each chunk's words arrive chunk-relative (offsets into the chunk's audio) and are moved to compact time.
- A word is kept only by the chunk that owns its midpoint: owned_start_ms <= (start_ms + end_ms) / 2 <
  owned_end_ms. A midpoint exactly on a split belongs to the later chunk; a midpoint at the very end of the audio
  belongs to the last chunk. Every other copy, whole or cut, is dropped.
- Guarantee: any word no longer than `overlap_ms` lies wholly inside the audio of the chunk that owns it (it can
  reach at most half its length, so at most overlap_ms / 2, past the owned boundary), and the cut copy another chunk
  hears has its midpoint on the owner's side, so it is dropped. Each such word therefore appears exactly once and
  is never split. Words longer than `overlap_ms` (rare: 500 ms covers nearly all spoken words) may be heard cut by
  both chunks and are kept from each side; that is the limit of overlap without knowing words in advance.
"""

from __future__ import annotations

import operator
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from sabha_asr.words import Word
from sabha_core.timemap import SegmentMap

DEFAULT_MAX_CHUNK_MS = 30_000
"""Longest chunk sent to the ASR (P3.5: "at most ~30 s", the window of Whisper-style models)."""

DEFAULT_OVERLAP_MS = 500
"""Audio shared by two chunks at a split inside speech (P3.5: 0.5 s)."""


@dataclass(frozen=True, slots=True)
class Chunk:
    """One ASR request: send compact audio [start_ms, end_ms); keep the words whose midpoint is in the owned region."""

    index: int
    start_ms: int
    end_ms: int
    owned_start_ms: int
    owned_end_ms: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_ms <= self.owned_start_ms < self.owned_end_ms <= self.end_ms:
            raise ValueError(f"chunk must satisfy 0 <= start <= owned_start < owned_end <= end: {self}")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def compact_joins(segment_map: SegmentMap) -> tuple[int, ...]:
    """Compact times where silence was cut out: the starts of segments that do not touch the previous one.

    Touching segments (a hand-built map may have them) have no silence between them, so speech may run across that
    point and it is not a safe place to cut.
    """
    segments = segment_map.segments
    return tuple(
        segment.compact_start_ms
        for previous, segment in pairwise(segments)
        if segment.orig_start_ms > previous.orig_end_ms
    )


def _split(start_ms: int, end_ms: int, max_chunk_ms: int, overlap_ms: int) -> list[tuple[int, int, int, int]]:
    """Split one piece of speech longer than max_chunk_ms into (start, end, owned_start, owned_end) parts."""
    length = end_ms - start_ms
    step = max_chunk_ms - overlap_ms  # longest owned region that still fits with overlap on both sides
    parts = -(-length // step)
    bounds = [start_ms + length * k // parts for k in range(parts + 1)]
    half = overlap_ms // 2
    planned = []
    for k in range(parts):
        owned_start, owned_end = bounds[k], bounds[k + 1]
        audio_start = owned_start - half if k > 0 else owned_start
        audio_end = owned_end + half if k < parts - 1 else owned_end
        planned.append((max(audio_start, start_ms), min(audio_end, end_ms), owned_start, owned_end))
    return planned


def plan_chunks(
    compact_length_ms: int,
    joins_ms: Iterable[int],
    *,
    max_chunk_ms: int = DEFAULT_MAX_CHUNK_MS,
    overlap_ms: int = DEFAULT_OVERLAP_MS,
) -> tuple[Chunk, ...]:
    """Plan the ASR chunks for compact audio of `compact_length_ms`. See the module docstring for the rules.

    `joins_ms` are the VAD joins in compact time (usually `compact_joins(segment_map)`), in any order; duplicates,
    0 and the compact end are ignored, and a join outside [0, compact_length_ms] raises ValueError. `overlap_ms`
    must be even (it is split equally either side of a split) and `max_chunk_ms` at least twice `overlap_ms` (so
    the overlap of a split never reaches past a VAD join). Empty audio gives no chunks.
    """
    length, max_chunk_ms, overlap_ms = (operator.index(v) for v in (compact_length_ms, max_chunk_ms, overlap_ms))
    if length < 0:
        raise ValueError(f"compact_length_ms cannot be negative, got {length}")
    if overlap_ms < 0 or overlap_ms % 2:
        raise ValueError(f"overlap_ms must be even and not negative, got {overlap_ms}")
    if max_chunk_ms <= 0 or max_chunk_ms < 2 * overlap_ms:
        raise ValueError(f"max_chunk_ms must be positive and at least 2 * overlap_ms, got {max_chunk_ms}")
    cuts = set()
    for raw in joins_ms:
        join = operator.index(raw)
        if not 0 <= join <= length:
            raise ValueError(f"join at {join} ms is outside the compact audio [0, {length}]")
        if 0 < join < length:
            cuts.add(join)
    if length == 0:
        return ()

    points = [0, *sorted(cuts), length]
    planned: list[tuple[int, int, int, int]] = []
    open_start: int | None = None  # the chunk being packed: [open_start, open_end)
    open_end = 0
    for piece_start, piece_end in pairwise(points):
        if piece_end - piece_start > max_chunk_ms:
            if open_start is not None:
                planned.append((open_start, open_end, open_start, open_end))
                open_start = None
            planned.extend(_split(piece_start, piece_end, max_chunk_ms, overlap_ms))
        elif open_start is not None and piece_end - open_start <= max_chunk_ms:
            open_end = piece_end
        else:
            if open_start is not None:
                planned.append((open_start, open_end, open_start, open_end))
            open_start, open_end = piece_start, piece_end
    if open_start is not None:
        planned.append((open_start, open_end, open_start, open_end))
    return tuple(Chunk(index, *bounds) for index, bounds in enumerate(planned))


def merge_chunk_words(chunk_words: Iterable[tuple[Chunk, Sequence[Word]]]) -> list[Word]:
    """Combine each chunk's chunk-relative words into one list on the compact timeline, sorted by (start, end).

    De-duplication follows the owned-region rule in the module docstring. A word ending past its chunk's audio is
    clamped to the audio end (providers overshoot the end of audio by a few ms); a word starting past it raises
    ValueError. The chunks must be the whole plan: their owned regions must tile [0, end) with no gap or repeat, or
    ValueError is raised, because a missing chunk would otherwise silently drop its words.
    """
    pairs = sorted(chunk_words, key=lambda pair: pair[0].owned_start_ms)
    if not pairs:
        return []
    expected_start = 0
    for chunk, _ in pairs:
        if chunk.owned_start_ms != expected_start:
            raise ValueError(
                f"chunks do not cover the audio: chunk {chunk.index} owns from {chunk.owned_start_ms} ms, "
                f"expected {expected_start} ms (a chunk is missing or repeated)"
            )
        expected_start = chunk.owned_end_ms
    audio_end = expected_start

    merged = []
    for chunk, words in pairs:
        owned_from, owned_to = 2 * chunk.owned_start_ms, 2 * chunk.owned_end_ms  # compare doubled midpoints exactly
        for word in words:
            if word.start_ms > chunk.duration_ms:
                raise ValueError(
                    f"word {word.text!r} starts at {word.start_ms} ms, outside chunk {chunk.index}'s "
                    f"{chunk.duration_ms} ms of audio"
                )
            placed = Word(
                word.text,
                chunk.start_ms + word.start_ms,
                chunk.start_ms + min(word.end_ms, chunk.duration_ms),
                word.confidence,
            )
            midpoint2 = placed.start_ms + placed.end_ms
            if owned_from <= midpoint2 < owned_to or (midpoint2 == owned_to == 2 * audio_end):
                merged.append(placed)
    merged.sort(key=lambda w: (w.start_ms, w.end_ms))
    return merged
