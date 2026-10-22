"""The transcribe stage: speech to text (plan task P3.5; queue gpu.speech).

`work(ctx)`:

1. Reads the preprocess stage's `compact.wav` and `segments@v1.json`. Missing: PermanentError `missing_input`.
2. Plans chunks with sabha_asr.chunking: cut at the VAD joins, at most the provider's limit (Sarvam: 29.5 s), with
   0.5 s overlap only where a long stretch of talk must be split.
3. Sends the chunks through the Transcriber (sabha_asr.transcriber: the configured provider, and fallbacks only
   when ASR_FALLBACKS names them; golden rule 7) in batches of BATCH_SIZE. Each finished batch is saved under
   `parts/` in this stage's folder, so a retry after a failure resumes there instead of sending (and paying for)
   the earlier batches again. A part is used only if it was made for the same chunk plan.
4. Merges the words (owned-region rule, sabha_asr.chunking.merge_chunk_words) and writes `asr@v1.json`: words
   {text, start_ms, end_ms, confidence} on the COMPACT timeline, language spans, and which provider and model
   answered (with any fallback reason).
5. Returns cost inputs for the stage run: audio seconds sent (chunk overlaps included), requests, provider, model,
   processing time and real-time factor. Prices are not applied here (billing, P8.6).

Errors: a retryable provider failure (timeout, 429, 5xx) is a TransientError, so the runner retries with backoff;
any other provider failure (bad key, no quota) is PermanentError `asr_failed`. Speech but no words at all:
NeedsReviewError `no_transcript`.

The cross-job batcher (sabha_asr.batcher) is for a self-hosted model on a GPU; a hosted API such as Sarvam takes
one request per chunk, so it is not used here.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import tempfile
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_asr.chunking import Chunk, compact_joins, merge_chunk_words, plan_chunks
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.transcriber import Transcriber
from sabha_asr.words import Word
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext, TransientError, Work

log = logging.getLogger("sabha.workers.transcribe")

VERSION = "asr@v1"
BATCH_SIZE = 10
NO_TRANSCRIPT = "no_transcript"
SAMPLE_RATE = 16_000
_BYTES_PER_MS = SAMPLE_RATE * 2 // 1000


@dataclass(frozen=True, slots=True)
class Part:
    """One finished batch, as saved under parts/."""

    provider: str
    model_id: str
    word_timing: str
    compute_ms: int
    fallback_reason: str | None
    results: list[ChunkResult]

    def to_json(self) -> bytes:
        return json.dumps({
            "provider": self.provider, "model_id": self.model_id, "word_timing": self.word_timing,
            "compute_ms": self.compute_ms, "fallback_reason": self.fallback_reason,
            "results": [
                {"chunk_id": r.chunk_id, "text": r.text, "words": [w.to_record() for w in r.words],
                 "languages": [[s.start_ms, s.end_ms, s.language] for s in r.languages]}
                for r in self.results
            ],
        }).encode()  # fmt: skip

    @classmethod
    def from_json(cls, raw: bytes) -> Part:
        data = json.loads(raw)
        results = [
            ChunkResult(
                r["chunk_id"], r["text"], tuple(Word.from_record(w) for w in r["words"]),
                tuple(LanguageSpan(s, e, lang) for s, e, lang in r["languages"]),
            )
            for r in data["results"]
        ]  # fmt: skip
        return cls(data["provider"], data["model_id"], data["word_timing"], data["compute_ms"],
                   data["fallback_reason"], results)  # fmt: skip


def plan_key(chunks: Sequence[Chunk]) -> str:
    """Identifies a chunk plan, so saved parts from a different plan (other limit, other audio) are never reused."""
    text = ";".join(f"{c.start_ms}-{c.end_ms}-{c.owned_start_ms}-{c.owned_end_ms}" for c in chunks)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)
    return buffer.getvalue()


def _cut(compact: Path, chunk: Chunk) -> AudioChunk:
    with wave.open(str(compact), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise PermanentError("missing_input", "compact.wav is not 16 kHz mono 16-bit PCM")
        wav.setpos(chunk.start_ms * SAMPLE_RATE // 1000)
        pcm = wav.readframes(chunk.duration_ms * SAMPLE_RATE // 1000)
    return AudioChunk(f"chunk-{chunk.index:04d}", _wav(pcm), chunk.duration_ms)


def _languages(chunks: Sequence[Chunk], results: Sequence[ChunkResult]) -> list[dict[str, Any]]:
    """Language spans on the compact timeline, each clipped to its chunk's owned region (no double counting)."""
    spans = []
    for chunk, result in zip(chunks, results, strict=True):
        for span in result.languages:
            start = max(chunk.start_ms + span.start_ms, chunk.owned_start_ms)
            end = min(chunk.start_ms + span.end_ms, chunk.owned_end_ms)
            if start < end:
                spans.append({"start_ms": start, "end_ms": end, "language": span.language})
    return spans


def make_work(transcriber: Callable[[], Transcriber], preprocess_version: str) -> Work:
    """The transcribe `work` function for StageRunner. `transcriber` returns the (cached) configured Transcriber."""

    def work(ctx: StageContext) -> dict[str, Any]:
        source = artefact_prefix(ctx.tenant_id, ctx.recording.id, "preprocess", preprocess_version)
        asr = transcriber()
        max_chunk_ms = min(p.max_chunk_ms for p in (asr.primary, *asr.fallbacks))
        with tempfile.TemporaryDirectory(prefix="sabha-transcribe-") as tmp:
            compact = Path(tmp) / "compact.wav"
            try:
                segment_map = SegmentMap.from_json(ctx.artefacts.get(source + "segments@v1.json"))
                ctx.artefacts.download(source + "compact.wav", compact)
            except FileNotFoundError as exc:
                raise PermanentError("missing_input", f"preprocess output not found: {exc}") from exc
            chunks = plan_chunks(segment_map.compact_length_ms, compact_joins(segment_map),
                                 max_chunk_ms=max_chunk_ms - max_chunk_ms % 2)  # fmt: skip
            if not chunks:
                raise PermanentError("missing_input", "compact.wav has no audio")
            key = plan_key(chunks)
            parts: list[Part] = []
            resumed = 0
            for first in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[first : first + BATCH_SIZE]
                part_key = f"{ctx.prefix}parts/{key}-{first // BATCH_SIZE:04d}.json"
                try:
                    parts.append(Part.from_json(ctx.artefacts.get(part_key)))
                    resumed += 1
                    continue
                except FileNotFoundError:
                    pass
                try:
                    outcome = asr.transcribe([_cut(compact, chunk) for chunk in batch])
                except ProviderError as exc:
                    error = TransientError if exc.retryable else PermanentError
                    code = "asr_unavailable" if exc.retryable else "asr_failed"
                    raise error(code, f"{exc.provider}: {exc.reason}") from exc
                part = Part(outcome.provider, outcome.model_id, outcome.word_timing, outcome.compute_ms,
                            outcome.fallback_reason, outcome.results)  # fmt: skip
                ctx.artefacts.put(part_key, part.to_json(), "application/json")
                parts.append(part)
        results = [result for part in parts for result in part.results]
        words = merge_chunk_words((c, r.words) for c, r in zip(chunks, results, strict=True))
        if not words:
            raise NeedsReviewError(NO_TRANSCRIPT, "speech was found but the ASR returned no words")
        providers = sorted({p.provider for p in parts})
        models = sorted({p.model_id for p in parts})
        fallbacks = sorted({p.fallback_reason for p in parts if p.fallback_reason})
        document = {
            "version": VERSION,
            "timeline": "compact",
            "provider": providers[0] if len(providers) == 1 else providers,
            "model": models[0] if len(models) == 1 else models,
            "word_timing": parts[0].word_timing,
            "fallback_reasons": fallbacks,
            "chunks": len(chunks),
            "words": [w.to_record() for w in words],
            "languages": _languages(chunks, results),
        }
        ctx.artefacts.put(ctx.prefix + "asr@v1.json", json.dumps(document, ensure_ascii=False).encode(),
                          "application/json")  # fmt: skip
        audio_ms = segment_map.compact_length_ms
        compute_ms = sum(p.compute_ms for p in parts)
        meta = {
            "provider": document["provider"],
            "model": document["model"],
            "requests": len(chunks),
            "sent_audio_s": round(sum(c.duration_ms for c in chunks) / 1000, 1),
            "audio_s": round(audio_ms / 1000, 1),
            "processing_s": round(compute_ms / 1000, 1),
            "real_time_factor": round(compute_ms / audio_ms, 4) if audio_ms else None,
            "batches_resumed": resumed,
            "fallback": bool(fallbacks),
            "words": len(words),
        }
        log.info("transcribed", extra={"recording_id": ctx.recording.id, **meta})
        return meta

    return work
