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

Speed-up (experimental, ASR_SPEEDUP): with `speed` above 1, each chunk is sped up with ffmpeg's atempo (pitch kept)
just before it is sent, so the provider bills fewer seconds. Chunks are planned `speed` times longer in compact time,
so the sped-up audio still fits the provider's limit. The provider's chunk-relative times are multiplied by `speed`
as soon as they come back, so parts, merging and everything after work on the compact timeline as usual. asr@v1.json
and the stage run record the factor. Saved parts are keyed by it, so a changed factor never reuses them.

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

from sabha_asr.assembly import WORD_TIMINGS, WordTiming
from sabha_asr.chunking import Chunk, compact_joins, merge_chunk_words, plan_chunks
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.transcriber import Transcriber
from sabha_asr.words import Word
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_workers.stages.preprocess import Runner, ffmpeg_timeout_s, run_tool
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext, TransientError, Work
from sabha_workers.stages.transcript import AsrOutput, TranscriptDeps, finish_transcript

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
    word_timing: WordTiming
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
        timing = data["word_timing"]
        if timing not in WORD_TIMINGS:
            raise ValueError(f"saved part has an unknown word_timing {timing!r}")
        return cls(data["provider"], data["model_id"], timing, data["compute_ms"],
                   data["fallback_reason"], results)  # fmt: skip


def plan_key(chunks: Sequence[Chunk], speed: float = 1.0) -> str:
    """Identifies a chunk plan, so saved parts from a different plan (other limit, other audio, other speed-up) are
    never reused."""
    text = ";".join(f"{c.start_ms}-{c.end_ms}-{c.owned_start_ms}-{c.owned_end_ms}" for c in chunks)
    if speed != 1.0:
        text += f";x{speed}"
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


def sent_ms(chunk: Chunk, speed: float) -> int:
    """How much audio is sent for `chunk`: its length divided by the speed-up."""
    return round(chunk.duration_ms / speed)


def _speed_up(audio: AudioChunk, chunk: Chunk, speed: float, tmp: Path, run: Runner) -> AudioChunk:
    """The chunk sped up `speed` times with ffmpeg atempo (pitch kept), trimmed or padded to exactly sent_ms."""
    source, target = tmp / f"{audio.chunk_id}.wav", tmp / f"{audio.chunk_id}-fast.wav"
    source.write_bytes(audio.wav)
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-protocol_whitelist", "file", "-i", str(source),
        "-af", f"atempo={speed}", "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", "-y",
        str(target),
    ]  # fmt: skip
    result = run(args, ffmpeg_timeout_s(chunk.duration_ms))
    if result.returncode != 0:
        raise PermanentError("speedup_failed", result.stderr.decode("utf-8", errors="replace").strip()[-500:])
    with wave.open(str(target), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    duration_ms = sent_ms(chunk, speed)
    size = duration_ms * _BYTES_PER_MS  # atempo can be a few ms off; a fixed length keeps the time scaling exact
    pcm = pcm[:size].ljust(size, b"\x00")
    source.unlink()
    target.unlink()
    return AudioChunk(audio.chunk_id, _wav(pcm), duration_ms)


def _slow_down(result: ChunkResult, chunk: Chunk, speed: float) -> ChunkResult:
    """Times from sped-up audio back to the chunk's own (compact) milliseconds, kept inside the chunk."""

    def back(ms: int) -> int:
        return min(round(ms * speed), chunk.duration_ms)

    words = tuple(Word(w.text, back(w.start_ms), back(w.end_ms), w.confidence) for w in result.words)
    languages = tuple(LanguageSpan(back(s.start_ms), back(s.end_ms), s.language) for s in result.languages)
    return ChunkResult(result.chunk_id, result.text, words, languages)


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


def make_work(
    transcriber: Callable[[], Transcriber],
    preprocess_version: str,
    transcript: TranscriptDeps,
    *,
    speed: float = 1.0,
    run: Runner = run_tool,
) -> Work:
    """The transcribe `work` function for StageRunner. `transcriber` returns the (cached) configured Transcriber.
    `speed` above 1 sends sped-up audio (ASR_SPEEDUP, see the module docstring); `run` runs ffmpeg for it.

    After the words, sabha_workers.stages.transcript assigns speaker roles and writes the canonical transcript
    (P3.6, P3.7), so one stage takes the recording from TRANSCRIBING to ANALYZING (or NEEDS_REVIEW)."""

    def work(ctx: StageContext) -> dict[str, Any]:
        source = artefact_prefix(ctx.tenant_id, ctx.recording.id, "preprocess", preprocess_version)
        asr = transcriber()
        # In compact time: a chunk planned `speed` times longer is sent no longer than the provider's limit.
        max_chunk_ms = int(min(p.max_chunk_ms for p in (asr.primary, *asr.fallbacks)) * speed)
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
            key = plan_key(chunks, speed)
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
                audio = [_cut(compact, chunk) for chunk in batch]
                if speed != 1.0:
                    audio = [_speed_up(a, c, speed, Path(tmp), run) for a, c in zip(audio, batch, strict=True)]
                try:
                    outcome = asr.transcribe(audio)
                except ProviderError as exc:
                    error = TransientError if exc.retryable else PermanentError
                    code = "asr_unavailable" if exc.retryable else "asr_failed"
                    raise error(code, f"{exc.provider}: {exc.reason}") from exc
                results = outcome.results
                if speed != 1.0:
                    results = [_slow_down(r, c, speed) for r, c in zip(results, batch, strict=True)]
                part = Part(outcome.provider, outcome.model_id, outcome.word_timing, outcome.compute_ms,
                            outcome.fallback_reason, results)  # fmt: skip
                ctx.artefacts.put(part_key, part.to_json(), "application/json")
                parts.append(part)
        results = [result for part in parts for result in part.results]
        words = merge_chunk_words((c, r.words) for c, r in zip(chunks, results, strict=True))
        if not words:
            raise NeedsReviewError(NO_TRANSCRIPT, "speech was found but the ASR returned no words")
        providers = sorted({p.provider for p in parts})
        models = sorted({p.model_id for p in parts})
        fallbacks = sorted({p.fallback_reason for p in parts if p.fallback_reason})
        languages = _languages(chunks, results)
        document = {
            "version": VERSION,
            "timeline": "compact",
            "provider": providers[0] if len(providers) == 1 else providers,
            "model": models[0] if len(models) == 1 else models,
            "word_timing": parts[0].word_timing,
            "speed": speed,
            "fallback_reasons": fallbacks,
            "chunks": len(chunks),
            "words": [w.to_record() for w in words],
            "languages": languages,
        }
        ctx.artefacts.put(ctx.prefix + "asr@v1.json", json.dumps(document, ensure_ascii=False).encode(),
                          "application/json")  # fmt: skip
        audio_ms = segment_map.compact_length_ms
        compute_ms = sum(p.compute_ms for p in parts)
        meta = {
            "provider": document["provider"],
            "model": document["model"],
            "requests": len(chunks),
            "sent_audio_s": round(sum(sent_ms(c, speed) for c in chunks) / 1000, 1),
            "speed": speed,
            "audio_s": round(audio_ms / 1000, 1),
            "processing_s": round(compute_ms / 1000, 1),
            "real_time_factor": round(compute_ms / audio_ms, 4) if audio_ms else None,
            "batches_resumed": resumed,
            "fallback": bool(fallbacks),
            "words": len(words),
        }
        log.info("transcribed", extra={"recording_id": ctx.recording.id, **meta})
        # What each model was sent, overlaps included: what the provider bills (by audio duration).
        billed: dict[str, int] = {}
        for i, part in enumerate(parts):
            batch = chunks[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
            billed[part.model_id] = billed.get(part.model_id, 0) + sum(sent_ms(c, speed) for c in batch)
        asr_output = AsrOutput(words, "+".join(models), parts[0].word_timing, languages, segment_map, billed)
        return {**meta, **finish_transcript(ctx, asr_output, transcript)}

    return work
