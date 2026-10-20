"""A provider that returns canned words without any network or model: for tests and local development only.

Settings refuse it in staging and production. Each chunk gets `script[chunk_id]`, or DEFAULT_TEXT, spread across
the chunk's duration with `spread_words`. Set `failure` to make every call raise it (for fallback tests); `calls`
records the chunk ids of every call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError, spread_words

DEFAULT_TEXT = "yeh ek fake transcript hai"


class FakeProvider:
    def __init__(
        self,
        *,
        name: str = "fake",
        script: Mapping[str, str] | None = None,
        language: str | None = "hi-IN",
        failure: ProviderError | None = None,
        max_chunk_ms: int = 30_000,
    ) -> None:
        self._name = name
        self._script = dict(script or {})
        self._language = language
        self._max_chunk_ms = max_chunk_ms
        self.failure = failure
        self.calls: list[list[str]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_id(self) -> str:
        return f"{self._name}/canned"

    @property
    def word_timing(self) -> WordTiming:
        return "approximate"

    @property
    def max_chunk_ms(self) -> int:
        return self._max_chunk_ms

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        self.calls.append([chunk.chunk_id for chunk in chunks])
        if self.failure is not None:
            raise self.failure
        results = []
        for chunk in chunks:
            text = self._script.get(chunk.chunk_id, DEFAULT_TEXT)
            words = tuple(spread_words(text, 0, chunk.duration_ms))
            languages = (LanguageSpan(0, chunk.duration_ms, self._language),)
            results.append(ChunkResult(chunk.chunk_id, " ".join(w.text for w in words), words, languages))
        return results
