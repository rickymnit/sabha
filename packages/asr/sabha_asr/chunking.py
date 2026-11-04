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
- Speaker changes (`speaker_cuts_ms`, from the diarization by `speaker_cuts`) are HARD cuts: no chunk crosses one,
  so no ASR phrase spans two speakers. The provider times phrases, not words (ADR 0006), and a phrase that ran across
  a change of speaker had its words spread across both turns, some landing on the wrong speaker. A speaker cut that
  falls inside speech gets the same protection as a split: each neighbour's audio reaches `overlap_ms / 2` past it,
  and the owned-region rule below keeps each word once. A speaker cut within `overlap_ms / 2` of a VAD join moves to
  the join, where no overlap is needed. Chunks that border such a cut are planned that much shorter, so their audio
  still fits `max_chunk_ms`. A speaker change in a pause (`quiet_cuts_ms`: at least `overlap_ms` with neither speaker
  talking) is cut in the middle of the pause with no overlap, like a VAD join, so it costs no extra audio.
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

from sabha_asr.words import Turn, Word
from sabha_core.timemap import SegmentMap

DEFAULT_MAX_CHUNK_MS = 30_000
"""Longest chunk sent to the ASR (P3.5: "at most ~30 s", the window of Whisper-style models)."""

DEFAULT_OVERLAP_MS = 500
"""Audio shared by two chunks at a split inside speech (P3.5: 0.5 s)."""

DEFAULT_MIN_SPEAKER_RUN_MS = 300
"""A speaker change is cut only between stretches of at least this much talk by each side, about one short word.
Sarvam times a whole chunk as one phrase, so a reply left inside the other speaker's chunk ("sir, any", 0.4 s) had
its words placed by guesswork and given to the wrong speaker; 1 s (the first value) left too many such replies. An
unmeasured starting value: tune it on the gold set (eval/wer.py, eval/roles.py)."""

DEFAULT_DOMINANT_SHARE = 0.8
"""A chunk in which one speaker does at least this share of the talk is that speaker's (chunk_turns)."""

DEFAULT_RUN_JOIN_GAP_MS = 1_000
"""Turns of one speaker separated by at most this much are one stretch of talk (as roles.DEFAULT_TURN_JOIN_GAP_MS)."""


@dataclass(frozen=True, slots=True)
class SpeakerCuts:
    """Where speakers change: `quiet` in a pause of at least the overlap (cut with none), `inside` everywhere else."""

    quiet: tuple[int, ...]
    inside: tuple[int, ...]


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


def speaker_cuts(
    turns: Iterable[Turn],
    *,
    min_run_ms: int = DEFAULT_MIN_SPEAKER_RUN_MS,
    join_gap_ms: int = DEFAULT_RUN_JOIN_GAP_MS,
    overlap_ms: int = DEFAULT_OVERLAP_MS,
) -> SpeakerCuts:
    """Compact times where one speaker hands over to another, for `plan_chunks(speaker_cuts_ms=cuts.inside,
    quiet_cuts_ms=cuts.quiet)`.

    Turns are taken in order of start and joined into stretches of one speaker (gaps up to `join_gap_ms`). Stretches
    shorter than `min_run_ms` are dropped, and the stretches either side of them joined when they are the same
    speaker, so a short reply never causes a cut. Between two stretches of different speakers the cut is the midpoint
    of the gap between them, or of their overlap when they overlap. A cut whose gap is at least `overlap_ms` is quiet.
    Each tuple is sorted, without duplicates.
    """
    runs: list[tuple[str, int, int]] = []
    for turn in sorted(turns, key=lambda t: (t.start_ms, t.end_ms)):
        if runs and runs[-1][0] == turn.speaker_label and turn.start_ms - runs[-1][2] <= join_gap_ms:
            runs[-1] = (turn.speaker_label, runs[-1][1], max(runs[-1][2], turn.end_ms))
        else:
            runs.append((turn.speaker_label, turn.start_ms, turn.end_ms))
    kept: list[tuple[str, int, int]] = []
    for label, start, end in runs:
        if end - start < min_run_ms:
            continue
        if kept and kept[-1][0] == label:
            kept[-1] = (label, kept[-1][1], max(kept[-1][2], end))
        else:
            kept.append((label, start, end))
    quiet = {(a[2] + b[1]) // 2 for a, b in pairwise(kept) if b[1] - a[2] >= overlap_ms}
    inside = {(a[2] + b[1]) // 2 for a, b in pairwise(kept) if b[1] - a[2] < overlap_ms} - quiet
    return SpeakerCuts(tuple(sorted(quiet)), tuple(sorted(inside)))


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
    speaker_cuts_ms: Iterable[int] = (),
    quiet_cuts_ms: Iterable[int] = (),
) -> tuple[Chunk, ...]:
    """Plan the ASR chunks for compact audio of `compact_length_ms`. See the module docstring for the rules.

    `joins_ms` are the VAD joins in compact time (usually `compact_joins(segment_map)`), in any order; duplicates,
    0 and the compact end are ignored, and a join outside [0, compact_length_ms] raises ValueError. `overlap_ms`
    must be even (it is split equally either side of a split) and `max_chunk_ms` at least twice `overlap_ms` (so
    the overlap of a split never reaches past a VAD join). `speaker_cuts_ms` are hard cuts at speaker changes
    (usually `speaker_cuts(turns)`); like joins, those outside (0, compact_length_ms) are ignored or raise. With any
    speaker cut, `max_chunk_ms` must be at least three times `overlap_ms`. `quiet_cuts_ms` are hard cuts in a pause:
    no chunk crosses them and no overlap is added. Empty audio gives no chunks.
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
    half = overlap_ms // 2
    hard: set[int] = set()  # speaker changes: no chunk crosses one
    for raw in speaker_cuts_ms:
        cut = operator.index(raw)
        if not 0 <= cut <= length:
            raise ValueError(f"speaker cut at {cut} ms is outside the compact audio [0, {length}]")
        if 0 < cut < length:
            near = [join for join in cuts if abs(join - cut) <= half]
            hard.add(min(near, key=lambda join: abs(join - cut)) if near else cut)
    quiet: set[int] = set()  # speaker changes in a pause: hard, but no overlap
    for raw in quiet_cuts_ms:
        cut = operator.index(raw)
        if not 0 <= cut <= length:
            raise ValueError(f"quiet cut at {cut} ms is outside the compact audio [0, {length}]")
        if 0 < cut < length:
            quiet.add(cut)
    hard |= quiet
    if hard - quiet - cuts and max_chunk_ms < 3 * overlap_ms:
        raise ValueError(f"with speaker cuts, max_chunk_ms must be at least 3 * overlap_ms, got {max_chunk_ms}")
    if length == 0:
        return ()

    def pad(point: int) -> int:
        """Audio added past a chunk boundary: half the overlap at a speaker cut inside speech, else none."""
        return half if point in hard and point not in cuts and point not in quiet else 0

    points = sorted({0, length, *cuts, *hard})
    planned: list[tuple[int, int, int, int]] = []
    open_start: int | None = None  # the chunk being packed: [open_start, open_end)
    open_end = 0

    def close() -> None:
        if open_start is not None:
            audio = (max(0, open_start - pad(open_start)), min(length, open_end + pad(open_end)))
            planned.append((*audio, open_start, open_end))

    for piece_start, piece_end in pairwise(points):
        if piece_end - piece_start + pad(piece_start) + pad(piece_end) > max_chunk_ms:
            close()
            open_start = None
            padded = pad(piece_start) or pad(piece_end)
            parts = _split(piece_start, piece_end, max_chunk_ms - (overlap_ms if padded else 0), overlap_ms)
            start, end, owned_start, owned_end = parts[0]
            parts[0] = (max(0, start - pad(piece_start)), end, owned_start, owned_end)
            start, end, owned_start, owned_end = parts[-1]
            parts[-1] = (start, min(length, end + pad(piece_end)), owned_start, owned_end)
            planned.extend(parts)
        elif (
            open_start is not None
            and open_end not in hard
            and piece_end - open_start + pad(open_start) + pad(piece_end) <= max_chunk_ms
        ):
            open_end = piece_end
        else:
            close()
            open_start, open_end = piece_start, piece_end
    close()
    return tuple(Chunk(index, *bounds) for index, bounds in enumerate(planned))


def _on_speech(ms: int, first: int, last: int, speech: Sequence[tuple[int, int]], talk: int, *, start: bool) -> int:
    """The point as far along `speech` (total `talk`) as `ms` is along [first, last]. A point exactly where one
    stretch of speech ends is the end of that stretch for a word's end, and the start of the next for a word's start,
    so no word spans a pause."""
    target = (ms - first) * talk / (last - first)
    for a, b in speech:
        if target < b - a or (target == b - a and not start):
            return round(a + target)
        target -= b - a
    return speech[-1][1]


def chunk_turns(
    chunks: Sequence[Chunk], turns: Sequence[Turn], *, dominant_share: float = DEFAULT_DOMINANT_SHARE
) -> list[Turn]:
    """The turns to give words to speakers by: one turn per chunk where one speaker dominates it.

    Chunks are cut at every change of speaker (`speaker_cuts`), so each is one speaker's stretch of talk. Matching
    each word to the diarizer's turns by time instead let slivers of the other speaker inside the stretch (flicker
    inside a word, a reply under 0.3 s) take words, because a phrase-timed provider gives word times by guesswork.
    So where one speaker does at least `dominant_share` of the talk in a chunk's owned region, that region becomes
    one turn of theirs; elsewhere the diarizer's turns are kept, clipped to the region. Sorted by start.
    """
    out: list[Turn] = []
    for chunk in chunks:
        lo, hi = chunk.owned_start_ms, chunk.owned_end_ms
        inside = [Turn(t.speaker_label, max(t.start_ms, lo), min(t.end_ms, hi)) for t in turns
                  if t.start_ms < hi and t.end_ms > lo]  # fmt: skip
        talk: dict[str, int] = {}
        for turn in inside:
            talk[turn.speaker_label] = talk.get(turn.speaker_label, 0) + turn.end_ms - turn.start_ms
        total = sum(talk.values())
        top = max(talk, key=lambda label: talk[label], default=None)
        if top is not None and talk[top] >= dominant_share * total:
            out.append(Turn(top, lo, hi))
        else:
            out.extend(inside)
    return sorted(out, key=lambda t: (t.start_ms, t.end_ms, t.speaker_label))


def retime_over_speech(words: Sequence[Word], speech: Sequence[tuple[int, int]]) -> list[Word]:
    """Words from a phrase-timed provider (word_timing "approximate"), moved off the pauses onto the speech.

    Such a provider times a phrase, and `spread_words` shares the phrase's time among its words by length as if the
    talk never paused. Sarvam often times a whole chunk as one phrase, so a word said after a short pause was placed
    in the pause or before it, and near a change of speaker it landed on the other speaker. Here each phrase (a run
    of words that touch, as spread_words leaves them) is spread over the SPEECH inside its span instead: `speech` is
    where someone is talking (diarization turns), in the same time as the words, sorted and not overlapping. Word
    order and the phrase's start and end are kept; a phrase with no speech inside it is left as it was.
    """
    out: list[Word] = []
    start = 0
    while start < len(words):
        end = start + 1
        while end < len(words) and words[end].start_ms == words[end - 1].end_ms:
            end += 1
        phrase = words[start:end]
        first, last = phrase[0].start_ms, phrase[-1].end_ms
        inside = [(max(a, first), min(b, last)) for a, b in speech if a < last and b > first]
        talk = sum(b - a for a, b in inside)
        if talk <= 0 or last <= first:
            out.extend(phrase)
        else:
            out.extend(
                Word(w.text, _on_speech(w.start_ms, first, last, inside, talk, start=True),
                     _on_speech(w.end_ms, first, last, inside, talk, start=False), w.confidence)
                for w in phrase
            )  # fmt: skip
        start = end
    return out


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
