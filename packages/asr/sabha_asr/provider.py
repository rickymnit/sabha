"""The interface every ASR provider implements, and its standard output (plan task P3.1, ADR 0006).

A provider transcribes a batch of audio chunks (the batcher in sabha_asr.batcher groups them) and returns, per chunk
and in the same order, its words with chunk-relative times. Every provider produces the same shapes, so the
transcribe stage never branches on which provider is active.

- `AudioChunk.wav` is 16 kHz mono 16-bit PCM WAV, cut from compact.wav (sabha_asr.chunking.plan_chunks).
- `ChunkResult.words` are `Word`s in chunk-relative milliseconds; `Word.shifted` moves them to compact time.
- `ChunkResult.languages` tags spans of the chunk with a BCP-47 language code, or None when not detected.
- `word_timing` is "word" when the provider times each word, "approximate" when it times phrases only and words are
  spread across each phrase with `spread_words`.

Errors: a provider raises `ProviderError` for every failure of the service (network, HTTP status, a response it
cannot read). `retryable` says whether trying the same request again later can succeed; the stage's retry policy
uses it. Anything else a provider raises is a bug and is never handled by a fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sabha_asr.assembly import WordTiming
from sabha_asr.words import Word


@dataclass(frozen=True, slots=True)
class AudioChunk:
    chunk_id: str
    wav: bytes
    duration_ms: int

    def __post_init__(self) -> None:
        if not self.chunk_id:
            raise ValueError("chunk_id must not be empty")
        if self.duration_ms <= 0:
            raise ValueError(f"chunk {self.chunk_id!r} must have a positive duration")


@dataclass(frozen=True, slots=True)
class LanguageSpan:
    """[start_ms, end_ms) of a chunk, chunk-relative, and its language (BCP-47, e.g. "hi-IN"), or None if unknown."""

    start_ms: int
    end_ms: int
    language: str | None


@dataclass(frozen=True, slots=True)
class ChunkResult:
    chunk_id: str
    text: str
    words: tuple[Word, ...]
    languages: tuple[LanguageSpan, ...]


class ProviderError(Exception):
    """The ASR service failed. `reason` is safe to log: it never holds audio, transcript text or keys."""

    def __init__(self, provider: str, reason: str, *, retryable: bool) -> None:
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason
        self.retryable = retryable


class AsrProvider(Protocol):
    @property
    def name(self) -> str:
        """Registry name, e.g. "sarvam"."""
        ...

    @property
    def model_id(self) -> str:
        """Provider and model, recorded in asr@v1.json and transcript@v1.json, e.g. "sarvam/saaras:v4"."""
        ...

    @property
    def word_timing(self) -> WordTiming: ...

    @property
    def max_chunk_ms(self) -> int:
        """The longest chunk the provider accepts; the chunk planner must not exceed it."""
        ...

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        """One result per chunk, in the same order. Raises ProviderError when the service fails."""
        ...


def spread_words(text: str, start_ms: int, end_ms: int) -> list[Word]:
    """Split a phrase timed [start_ms, end_ms) into words and share its time among them by length.

    For providers that time phrases, not words (ADR 0006). Each word gets time in proportion to its length in
    characters (Unicode code points, so Devanagari counts like Latin); the words tile the phrase with no gaps, the
    first starts at start_ms and the last ends at end_ms. Confidence is None: these providers give none. A phrase too
    short for its words yields some zero-length words, which `Word` allows.
    """
    if not 0 <= start_ms <= end_ms:
        raise ValueError(f"phrase times must satisfy 0 <= start_ms <= end_ms, got [{start_ms}, {end_ms})")
    tokens = text.split()
    if not tokens:
        return []
    total = sum(len(token) for token in tokens)
    duration = end_ms - start_ms
    words = []
    cursor, consumed = start_ms, 0
    for token in tokens:
        consumed += len(token)
        # Integer boundaries from the running total, so rounding never accumulates and the last word ends at end_ms.
        boundary = start_ms + duration * consumed // total
        words.append(Word(token, cursor, boundary, None))
        cursor = boundary
    return words
