"""Runs the configured ASR provider, and its explicit fallbacks only when configured (golden rule 7, ADR 0006).

`Transcriber(primary, fallbacks)` sends a batch to `primary`. If it raises ProviderError:
- with no fallbacks, the error is raised unchanged: the stage fails or retries, nothing is swapped;
- with fallbacks, each is tried in the configured order. Every switch is logged as a warning naming both providers
  and the reason, and the outcome records which provider answered and why (`fallback_reason`), so asr@v1.json and
  stage_runs show it. If every provider fails, the last error is raised.
Exceptions other than ProviderError are bugs and are never handled by a fallback.

The outcome also carries the real-time factor: compute time / audio time for the batch (lower is faster).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AsrProvider, AudioChunk, ChunkResult, ProviderError

log = logging.getLogger("sabha.asr")


@dataclass(frozen=True, slots=True)
class TranscribeOutcome:
    results: list[ChunkResult]
    provider: str
    model_id: str
    word_timing: WordTiming
    audio_ms: int
    compute_ms: int
    fallback_reason: str | None  # None when the primary provider answered

    @property
    def real_time_factor(self) -> float:
        return self.compute_ms / self.audio_ms if self.audio_ms else 0.0


class Transcriber:
    def __init__(
        self,
        primary: AsrProvider,
        fallbacks: Sequence[AsrProvider] = (),
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        names = [primary.name, *(f.name for f in fallbacks)]
        if len(set(names)) != len(names):
            raise ValueError(f"each ASR provider may appear once: {names}")
        self.primary = primary
        self.fallbacks = tuple(fallbacks)
        self._clock = clock

    def transcribe(self, chunks: Sequence[AudioChunk]) -> TranscribeOutcome:
        if not chunks:
            raise ValueError("nothing to transcribe")
        audio_ms = sum(chunk.duration_ms for chunk in chunks)
        failures: list[ProviderError] = []
        for provider in (self.primary, *self.fallbacks):
            too_long = [c.chunk_id for c in chunks if c.duration_ms > provider.max_chunk_ms]
            if too_long:
                raise ValueError(f"chunks longer than {provider.name}'s {provider.max_chunk_ms} ms limit: {too_long}")
            if failures:
                log.warning(
                    "ASR provider failed; using the configured fallback",
                    extra={
                        "failed_provider": failures[-1].provider,
                        "fallback_provider": provider.name,
                        "reason": failures[-1].reason,
                        "retryable": failures[-1].retryable,
                    },
                )
            started = self._clock()
            try:
                results = provider.transcribe(chunks)
            except ProviderError as exc:
                failures.append(exc)
                continue
            compute_ms = round((self._clock() - started) * 1000)
            if [r.chunk_id for r in results] != [c.chunk_id for c in chunks]:
                raise RuntimeError(f"{provider.name} returned results that do not match the chunks it was given")
            return TranscribeOutcome(
                results=results,
                provider=provider.name,
                model_id=provider.model_id,
                word_timing=provider.word_timing,
                audio_ms=audio_ms,
                compute_ms=compute_ms,
                fallback_reason="; ".join(f"{f.provider}: {f.reason}" for f in failures) or None,
            )
        raise failures[-1]
