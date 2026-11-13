"""The transcribe stage: speech to text (plan task P3.5; queue gpu.speech).

`work(ctx)`:

1. Reads the preprocess stage's `compact.wav` and `segments@v1.json`, and the diarize stage's turns. Missing:
   PermanentError `missing_input`.
2. Plans chunks with sabha_asr.chunking: cut at the VAD joins and at every change of speaker (so no ASR phrase spans
   two speakers), at most the provider's limit (Sarvam: 29.5 s), with 0.5 s overlap where talk must be split. A
   change of speaker in a pause is cut there with no overlap.
3. Sends the chunks through the Transcriber (sabha_asr.transcriber: the configured provider, and fallbacks only
   when ASR_FALLBACKS names them; golden rule 7) in batches of BATCH_SIZE. Each finished batch is saved under
   `parts/` in this stage's folder, so a retry after a failure resumes there instead of sending (and paying for)
   the earlier batches again. A part is used only if it was made for the same chunk plan.
   Then a short chunk (under LONG_CHUNK_MS) heard in a language none of the long chunks is in is asked again once,
   with the recording's main language as a hint (`off_language`); those answers are saved as one more part.
4. For a provider that times phrases, not words (Sarvam), moves each phrase's words off the pauses onto the speech
   the diarizer heard (sabha_asr.chunking.retime_over_speech). Merges the words (owned-region rule,
   sabha_asr.chunking.merge_chunk_words). Words are later given to the speaker whose stretch of talk their chunk is
   (sabha_asr.chunking.chunk_turns), not matched one by one to the diarizer's turns. and writes `asr@v1.json`: words
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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sabha_asr.assembly import WORD_TIMINGS, WordTiming
from sabha_asr.chunking import (
    Chunk,
    chunk_turns,
    compact_joins,
    merge_chunk_words,
    plan_chunks,
    retime_over_speech,
    speaker_cuts,
)
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.transcriber import Transcriber
from sabha_asr.words import Turn, Word
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


LONG_CHUNK_MS = 5_000
"""Chunks at least this long say which languages the recording is in; shorter ones may be asked again."""
MIN_LANGUAGE_SHARE = 0.05
"""A language is one of the recording's when it is at least this share of the long chunks' audio."""


def off_language(chunks: Sequence[Chunk], results: Sequence[ChunkResult]) -> tuple[str | None, list[int]]:
    """(the recording's main language, the indexes of short chunks to ask again with it as a hint).

    The provider detects the language of each chunk on its own, and on a clip of a second or two it can be wrong
    ("thik achhe" came back in Bengali script, "aamaanga" in Tamil, in a Hindi call). The languages of the long
    chunks are taken as the recording's; a short chunk heard in none of them is asked again with the main one. With
    no long chunk, or no language reported, nothing is asked again.
    """
    share: dict[str, int] = {}
    for chunk, result in zip(chunks, results, strict=True):
        if chunk.duration_ms >= LONG_CHUNK_MS:
            for span in result.languages:
                if span.language:
                    share[span.language] = share.get(span.language, 0) + span.end_ms - span.start_ms
    total = sum(share.values())
    if not total:
        return None, []
    main = {language for language, ms in share.items() if ms >= MIN_LANGUAGE_SHARE * total}
    again = [
        index
        for index, (chunk, result) in enumerate(zip(chunks, results, strict=True))
        if chunk.duration_ms < LONG_CHUNK_MS and any(s.language and s.language not in main for s in result.languages)
    ]
    return max(share, key=lambda language: share[language]), again


def _speech(turns: Sequence[dict[str, Any]]) -> list[tuple[int, int]]:
    """Where anyone is talking, from the diarization turns: their union, sorted."""
    out: list[tuple[int, int]] = []
    for start, end in sorted((t["start_ms"], t["end_ms"]) for t in turns):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _within(speech: Sequence[tuple[int, int]], chunk: Chunk) -> list[tuple[int, int]]:
    """The speech inside a chunk's audio, chunk-relative."""
    return [(max(a, chunk.start_ms) - chunk.start_ms, min(b, chunk.end_ms) - chunk.start_ms)
            for a, b in speech if a < chunk.end_ms and b > chunk.start_ms]  # fmt: skip


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
    transcriber: Callable[[str | None], Transcriber],
    preprocess_version: str,
    transcript: TranscriptDeps,
    *,
    speed: float = 1.0,
    run: Runner = run_tool,
) -> Work:
    """The transcribe `work` function for StageRunner. `transcriber(spec)` returns the (cached) Transcriber for the
    model chosen at upload (Recording.asr_choice), or the configured one for None.
    `speed` above 1 sends sped-up audio (ASR_SPEEDUP, see the module docstring); `run` runs ffmpeg for it.

    After the words, sabha_workers.stages.transcript assigns speaker roles and writes the canonical transcript
    (P3.6, P3.7), so one stage takes the recording from TRANSCRIBING to ANALYZING (or NEEDS_REVIEW)."""

    def work(ctx: StageContext) -> dict[str, Any]:
        source = artefact_prefix(ctx.tenant_id, ctx.recording.id, "preprocess", preprocess_version)
        diarized = artefact_prefix(ctx.tenant_id, ctx.recording.id, "diarize", transcript.diarize_version)
        asr = transcriber(ctx.recording.asr_choice)
        # In compact time: a chunk planned `speed` times longer is sent no longer than the provider's limit.
        max_chunk_ms = int(min(p.max_chunk_ms for p in (asr.primary, *asr.fallbacks)) * speed)
        with tempfile.TemporaryDirectory(prefix="sabha-transcribe-") as tmp:
            compact = Path(tmp) / "compact.wav"
            try:
                segment_map = SegmentMap.from_json(ctx.artefacts.get(source + "segments@v1.json"))
                turns = json.loads(ctx.artefacts.get(diarized + "diarization@v1.json"))["compact"]
                ctx.artefacts.download(source + "compact.wav", compact)
            except FileNotFoundError as exc:
                raise PermanentError("missing_input", f"preprocess output not found: {exc}") from exc
            cuts = speaker_cuts(Turn(t["speaker_label"], t["start_ms"], t["end_ms"]) for t in turns)
            chunks = plan_chunks(segment_map.compact_length_ms, compact_joins(segment_map),
                                 max_chunk_ms=max_chunk_ms - max_chunk_ms % 2, speaker_cuts_ms=cuts.inside,
                                 quiet_cuts_ms=cuts.quiet)  # fmt: skip
            if not chunks:
                raise PermanentError("missing_input", "compact.wav has no audio")
            key = plan_key(chunks, speed)

            def ask(batch: Sequence[Chunk], language: str | None) -> Part:
                audio = [replace(_cut(compact, chunk), language=language) for chunk in batch]
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
                return Part(outcome.provider, outcome.model_id, outcome.word_timing, outcome.compute_ms,
                            outcome.fallback_reason, results)  # fmt: skip

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
                part = ask(batch, None)
                ctx.artefacts.put(part_key, part.to_json(), "application/json")
                parts.append(part)
            results = [result for part in parts for result in part.results]
            timings = [part.word_timing for part in parts for _ in part.results]
            # Short chunks heard in a language the rest of the recording is not in are asked again (module docstring).
            hint, again = off_language(chunks, results)
            if hint is not None and again:
                retry_key = f"{ctx.prefix}parts/{key}-language.json"
                try:
                    retried = Part.from_json(ctx.artefacts.get(retry_key))
                except FileNotFoundError:
                    retried = ask([chunks[i] for i in again], hint)
                    ctx.artefacts.put(retry_key, retried.to_json(), "application/json")
                parts.append(retried)
                for index, result in zip(again, retried.results, strict=True):
                    results[index], timings[index] = result, retried.word_timing
        speech = _speech(turns)
        words = merge_chunk_words(
            (c, retime_over_speech(r.words, _within(speech, c)) if timing == "approximate" else r.words)
            for c, r, timing in zip(chunks, results, timings, strict=True)
        )
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
            "sent_audio_s": round(sum(sent_ms(c, speed) for c in (*chunks, *(chunks[i] for i in again))) / 1000, 1),
            "speed": speed,
            "audio_s": round(audio_ms / 1000, 1),
            "processing_s": round(compute_ms / 1000, 1),
            "real_time_factor": round(compute_ms / audio_ms, 4) if audio_ms else None,
            "batches_resumed": resumed,
            "language_retries": len(again),
            "fallback": bool(fallbacks),
            "words": len(words),
        }
        log.info("transcribed", extra={"recording_id": ctx.recording.id, **meta})
        # What each model was sent, overlaps included: what the provider bills (by audio duration).
        billed: dict[str, int] = {}
        batches = [list(chunks[i : i + BATCH_SIZE]) for i in range(0, len(chunks), BATCH_SIZE)]
        if again:
            batches.append([chunks[i] for i in again])
        for part, sent in zip(parts, batches, strict=True):
            billed[part.model_id] = billed.get(part.model_id, 0) + sum(sent_ms(c, speed) for c in sent)
        diarized_turns = [Turn(t["speaker_label"], t["start_ms"], t["end_ms"]) for t in turns]
        asr_output = AsrOutput(words, "+".join(models), parts[0].word_timing, languages, segment_map, billed,
                               word_turns=chunk_turns(chunks, diarized_turns))  # fmt: skip
        return {**meta, **finish_transcript(ctx, asr_output, transcript)}

    return work
