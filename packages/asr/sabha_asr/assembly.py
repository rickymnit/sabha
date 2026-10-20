"""Transcript assembly: ASR words + diarization turns + roles -> utterances on the ORIGINAL timeline (plan task P3.7).

Inputs are on the COMPACT timeline (ASR and diarization run on compact.wav). Output, transcript@v1.json, is on the
ORIGINAL recording timeline, mapped with sabha_core.timemap.SegmentMap.compact_to_original (golden rule 4).

Rules:

- Each word goes to one turn by sabha_asr.words.assign_words_to_turns: most overlap wins, ties go to the turn that
  started first, words overlapping no turn go to the nearest turn.
- Each word is placed in the segment holding its midpoint (a zero-length word at a join belongs to the later
  segment, as in timemap). A word whose ASR timestamps straddle a join is clamped to that segment, so no word ever
  covers removed silence. Its start maps with compact_to_original(start); its end, an exclusive bound, maps with
  compact_to_original(end - 1) + 1, so a word ending exactly at a join keeps its end in the earlier segment instead
  of jumping to the start of the next one. A zero-length word gets 1 ms, [start, start + 1), or [end - 1, end) at
  the end of its segment, as in word assignment, so every utterance has start_ms < end_ms (eval/ and the gold
  transcripts require that too).
- Words, in time order, are grouped into utterances: consecutive words of the same speaker form one utterance.
- Splitting at joins: an utterance never spans a removed silence of `split_silence_ms` or more (default 1500 ms,
  the timemap merge gap, so with default preprocessing every real join splits; touching segments and hand-built
  maps with small gaps do not). The removed silence between two words is the difference of their segments'
  original-minus-compact offsets. Reason: an utterance is played back and quoted as one span; spanning a long
  removed silence would make playback include that silence and make its original-time length overstate speech.
  Pauses inside one segment do not split (they are real time the speaker held the floor).
- avg_confidence is the mean confidence of the utterance's words that have one, rounded to 4 decimals, or None when
  none do (providers without word confidence, such as Sarvam: ADR 0006). low_confidence_spans are half-open
  [start, end) character ranges of `text` (Unicode code points) covering runs of consecutive words with confidence
  below `low_confidence_below`; the space between two low-confidence words is inside the span. A word without a
  confidence is never marked and ends a run.
- word_timing says how word times were obtained: "word" when the ASR timed each word, "approximate" when it timed
  only phrases and words were spread across them (sabha_asr.provider.spread_words). With approximate timing,
  speaker assignment and quote timestamps are only as precise as the phrases.
- Overlapping speech is kept: words of two speakers that interleave in time make alternating short utterances.

transcript@v1.json is documented by schemas/transcript.v1.schema.json (JSON Schema 2020-12, the contract);
`validate_transcript` enforces the same rules in code (standard library only) plus the ones JSON Schema cannot say.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any, Literal, TypedDict, TypeGuard

from sabha_asr.words import Turn, Word, assign_words_to_turns
from sabha_core.timemap import DEFAULT_MERGE_GAP_MS, SegmentMap

TRANSCRIPT_VERSION = "transcript@v1"
WordTiming = Literal["word", "approximate"]
TIMELINE = "original"

DEFAULT_SPLIT_SILENCE_MS = DEFAULT_MERGE_GAP_MS
"""An utterance never spans a removed silence this long or longer."""

DEFAULT_LOW_CONFIDENCE_BELOW = 0.5
"""Words below this ASR confidence are marked. A first choice: providers scale confidence differently, so tune it
per provider against the gold set once the provider is chosen."""

_SCHEMA_FILE = "transcript.v1.schema.json"
_TOP_KEYS = frozenset({"version", "timeline", "asr_model", "word_count", "utterances"})
_OPTIONAL_TOP_KEYS = frozenset({"word_timing"})  # absent in transcripts written before Sarvam (ADR 0006): "word"
WORD_TIMINGS = ("word", "approximate")
_UTTERANCE_KEYS = frozenset(
    {"role", "speaker_label", "start_ms", "end_ms", "text", "avg_confidence", "low_confidence_spans"}
)


class UtteranceRecord(TypedDict):
    role: str
    speaker_label: str
    start_ms: int
    end_ms: int
    text: str
    avg_confidence: float | None
    low_confidence_spans: list[list[int]]


class TranscriptRecord(TypedDict):
    """The transcript@v1.json content."""

    version: str
    timeline: str
    asr_model: str
    word_timing: WordTiming
    word_count: int
    utterances: list[UtteranceRecord]


@dataclass(frozen=True, slots=True)
class Utterance:
    """Consecutive words of one speaker. Times are on the ORIGINAL timeline."""

    role: str
    speaker_label: str
    start_ms: int
    end_ms: int
    text: str
    avg_confidence: float | None
    low_confidence_spans: tuple[tuple[int, int], ...]

    def to_record(self) -> UtteranceRecord:
        return {
            "role": self.role,
            "speaker_label": self.speaker_label,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "avg_confidence": self.avg_confidence,
            "low_confidence_spans": [[start, end] for start, end in self.low_confidence_spans],
        }


@dataclass(frozen=True, slots=True)
class _Placed:
    word: Word
    speaker_label: str
    segment_index: int
    orig_start_ms: int
    orig_end_ms: int


def _place(word: Word, segment_map: SegmentMap, compact_starts: Sequence[int]) -> tuple[int, int, int]:
    """(segment index, original start, original end) for one word. See the module docstring."""
    length = segment_map.compact_length_ms
    if not segment_map.segments:
        raise ValueError(f"word {word.text!r} cannot be placed: the segment map has no speech")
    if word.end_ms > length:
        raise ValueError(
            f"word {word.text!r} [{word.start_ms}, {word.end_ms}) is outside the compact audio [0, {length}]"
        )
    midpoint = (word.start_ms + word.end_ms) // 2  # within [start, end - 1] for a word of positive length
    index = bisect_right(compact_starts, midpoint) - 1
    segment = segment_map.segments[index]
    start = max(word.start_ms, segment.compact_start_ms)
    end = min(word.end_ms, segment.compact_end_ms)
    if end == start:  # a zero-length word gets 1 ms inside its segment, as in word assignment
        if end < segment.compact_end_ms:
            end += 1
        else:
            start -= 1
    return index, segment_map.compact_to_original(start), segment_map.compact_to_original(end - 1) + 1


def _utterance(group: Sequence[_Placed], role: str, low_confidence_below: float) -> Utterance:
    texts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    span_start: int | None = None
    for placed in group:
        if texts:
            cursor += 1  # the joining space
        word_end = cursor + len(placed.word.text)
        confidence = placed.word.confidence
        if confidence is not None and confidence < low_confidence_below:
            if span_start is None:
                span_start = cursor
            spans.append((span_start, word_end))
        else:
            span_start = None
        texts.append(placed.word.text)
        cursor = word_end
    known = [p.word.confidence for p in group if p.word.confidence is not None]
    merged: list[tuple[int, int]] = []
    for start, end in spans:  # spans of one run share their start; keep the longest
        if merged and merged[-1][0] == start:
            merged[-1] = (start, end)
        else:
            merged.append((start, end))
    return Utterance(
        role=role,
        speaker_label=group[0].speaker_label,
        start_ms=min(p.orig_start_ms for p in group),
        end_ms=max(p.orig_end_ms for p in group),
        text=" ".join(texts),
        avg_confidence=round(math.fsum(known) / len(known), 4) if known else None,
        low_confidence_spans=tuple(merged),
    )


def assemble_utterances(
    words: Sequence[Word],
    turns: Sequence[Turn],
    roles: Mapping[str, str],
    segment_map: SegmentMap,
    *,
    split_silence_ms: int = DEFAULT_SPLIT_SILENCE_MS,
    low_confidence_below: float = DEFAULT_LOW_CONFIDENCE_BELOW,
) -> list[Utterance]:
    """Group compact-time words into utterances on the original timeline. See the module docstring for the rules.

    `roles` maps speaker_label -> role (RoleAssignment.role_by_speaker()). Raises ValueError for a word outside the
    compact audio, words without turns, or a speaker with no role.
    """
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.start_ms, w.end_ms))
    compact_starts = [segment.compact_start_ms for segment in segment_map.segments]
    # Silence removed before each segment: original start minus compact start.
    offsets = [segment.orig_start_ms - segment.compact_start_ms for segment in segment_map.segments]
    placed = []
    for word, turn in zip(ordered, assign_words_to_turns(ordered, turns), strict=True):
        if turn.speaker_label not in roles:
            raise ValueError(f"speaker {turn.speaker_label!r} has no role in roles@v1")
        placed.append(_Placed(word, turn.speaker_label, *_place(word, segment_map, compact_starts)))

    utterances = []
    group = [placed[0]]
    for current in placed[1:]:
        previous = group[-1]
        removed_ms = offsets[current.segment_index] - offsets[previous.segment_index]
        if current.speaker_label != previous.speaker_label or removed_ms >= split_silence_ms:
            utterances.append(_utterance(group, roles[previous.speaker_label], low_confidence_below))
            group = []
        group.append(current)
    utterances.append(_utterance(group, roles[group[0].speaker_label], low_confidence_below))
    return utterances


def assemble_transcript(
    words: Sequence[Word],
    turns: Sequence[Turn],
    roles: Mapping[str, str],
    segment_map: SegmentMap,
    *,
    asr_model: str,
    word_timing: WordTiming = "word",
    split_silence_ms: int = DEFAULT_SPLIT_SILENCE_MS,
    low_confidence_below: float = DEFAULT_LOW_CONFIDENCE_BELOW,
) -> TranscriptRecord:
    """The transcript@v1.json content for one recording. The result passes `validate_transcript`."""
    utterances = assemble_utterances(
        words,
        turns,
        roles,
        segment_map,
        split_silence_ms=split_silence_ms,
        low_confidence_below=low_confidence_below,
    )
    transcript: TranscriptRecord = {
        "version": TRANSCRIPT_VERSION,
        "timeline": TIMELINE,
        "asr_model": asr_model,
        "word_timing": word_timing,
        "word_count": len(words),
        "utterances": [u.to_record() for u in utterances],
    }
    validate_transcript(transcript)
    return transcript


def load_transcript_schema() -> dict[str, Any]:
    """The transcript@v1 JSON Schema (the documented contract)."""
    text = resources.files("sabha_asr").joinpath("schemas", _SCHEMA_FILE).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


# --- validation --------------------------------------------------------------------------------------------------


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _non_blank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_utterance(path: str, utterance: object) -> tuple[int, int]:
    if not isinstance(utterance, dict):
        raise ValueError(f"{path} must be an object")
    if set(utterance) != _UTTERANCE_KEYS:
        raise ValueError(f"{path} must have exactly the keys {', '.join(sorted(_UTTERANCE_KEYS))}")
    for key in ("role", "speaker_label", "text"):
        if not _non_blank(utterance[key]):
            raise ValueError(f"{path}.{key} must be a non-blank string")
    start, end = utterance["start_ms"], utterance["end_ms"]
    if not (_is_int(start) and _is_int(end)) or start < 0:
        raise ValueError(f"{path} times must be whole milliseconds (int) and not negative")
    if end <= start:
        raise ValueError(f"{path} must end ({end} ms) after it starts ({start} ms)")
    confidence = utterance["avg_confidence"]
    if confidence is not None and (
        not isinstance(confidence, int | float) or isinstance(confidence, bool) or not 0 <= confidence <= 1
    ):
        raise ValueError(f"{path}.avg_confidence must be a number in [0, 1] or null")
    spans = utterance["low_confidence_spans"]
    if not isinstance(spans, list):
        raise ValueError(f"{path}.low_confidence_spans must be a list")
    text_length = len(utterance["text"])
    previous_end = 0
    for index, span in enumerate(spans):
        span_path = f"{path}.low_confidence_spans[{index}]"
        if not (isinstance(span, list) and len(span) == 2 and all(_is_int(v) for v in span)):
            raise ValueError(f"{span_path} must be a pair of whole numbers [start, end]")
        span_start, span_end = span
        if not 0 <= span_start < span_end <= text_length:
            raise ValueError(f"{span_path} must satisfy 0 <= start < end <= len(text) ({text_length})")
        if span_start < previous_end:
            raise ValueError(f"{span_path} overlaps or comes before the previous span")
        previous_end = span_end
    return start, end


def validate_transcript(doc: object) -> None:
    """Raise ValueError, naming the first problem, unless `doc` is valid transcript@v1 content."""
    if not isinstance(doc, dict):
        raise ValueError("transcript must be an object")
    if not _TOP_KEYS <= set(doc) <= _TOP_KEYS | _OPTIONAL_TOP_KEYS:
        raise ValueError(
            f"transcript must have the keys {', '.join(sorted(_TOP_KEYS))} and may have {', '.join(_OPTIONAL_TOP_KEYS)}"
        )
    if doc.get("word_timing", "word") not in WORD_TIMINGS:
        raise ValueError(f"word_timing must be one of {', '.join(WORD_TIMINGS)}")
    if doc["version"] != TRANSCRIPT_VERSION:
        raise ValueError(f"transcript version must be {TRANSCRIPT_VERSION!r}")
    if doc["timeline"] != TIMELINE:
        raise ValueError(f"transcript timeline must be {TIMELINE!r}: users only ever see original times")
    if not _non_blank(doc["asr_model"]):
        raise ValueError("asr_model must be a non-blank string")
    if not _is_int(doc["word_count"]) or doc["word_count"] < 0:
        raise ValueError("word_count must be a whole number, not negative")
    utterances = doc["utterances"]
    if not isinstance(utterances, list):
        raise ValueError("utterances must be a list")
    previous_start = 0
    for index, utterance in enumerate(utterances):
        start, _ = _check_utterance(f"utterances[{index}]", utterance)
        if start < previous_start:
            raise ValueError(f"utterances[{index}] starts before the previous utterance: they must be sorted")
        previous_start = start
