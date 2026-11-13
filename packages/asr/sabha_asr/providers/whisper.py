"""Self-hosted Whisper with faster-whisper (CTranslate2), on this machine's CPU or a GPU (docs/adr/0012-...).

Audio never leaves the machine and there is no per-minute fee: the cost is the hardware (sabha_asr.pricing gives
None). Installed only on request: `uv sync --extra whisper` (faster-whisper and its CTranslate2 wheels). The model
(ASR_MODEL, default large-v3-turbo) is downloaded from Hugging Face on first use into faster-whisper's cache.

Each chunk is decoded from its WAV bytes and transcribed with word timestamps (word_timing "word"); faster-whisper's
own VAD is off because the pipeline's chunks are already speech. A BCP-47 hint ("hi-IN") is passed as "hi";
"unknown" lets Whisper detect the language once per chunk (it picks ONE language per chunk, so Hindi-English
switching is written in whichever script it chose).

Sizes for a CPU-only machine: large-v3-turbo in int8 needs about 1.5 to 2 GB of RAM and runs slower than real time on
a few cores; `small` or `medium` are lighter and less accurate on Hindi. On a GPU use WHISPER_DEVICE=cuda and
WHISPER_COMPUTE_TYPE=float16.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Sequence
from typing import Any

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.words import Word

NAME = "whisper"
DEFAULT_MODEL = "large-v3-turbo"
MAX_CHUNK_MS = 29_500  # Whisper's window is 30 s

log = logging.getLogger("sabha.asr.whisper")


class WhisperProvider:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 0,
        language: str = "unknown",
        load: Callable[[], Any] | None = None,
    ) -> None:
        self._model_name = model
        self._language = language
        self._load = load or (lambda: _load(model, device, compute_type, cpu_threads))
        self._model: Any = None

    @property
    def name(self) -> str:
        return NAME

    @property
    def model_id(self) -> str:
        return f"{NAME}/{self._model_name}"

    @property
    def word_timing(self) -> WordTiming:
        return "word"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        if self._model is None:
            self._model = self._load()
        return [self._transcribe_one(chunk) for chunk in chunks]

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        hint = (chunk.language or self._language).split("-")[0]
        segments, info = self._model.transcribe(
            io.BytesIO(chunk.wav), language=None if hint in ("", "unknown") else hint, word_timestamps=True,
            vad_filter=False, beam_size=5, condition_on_previous_text=False,
        )  # fmt: skip
        words = []
        for segment in segments:  # a generator: decoding happens while iterating
            for item in segment.words or []:
                text = item.word.strip()
                if not text:
                    continue
                start = min(max(round(item.start * 1000), 0), chunk.duration_ms)
                end = min(max(round(item.end * 1000), start), chunk.duration_ms)
                words.append(Word(text, start, end, min(max(float(item.probability), 0.0), 1.0)))
        language = getattr(info, "language", None)
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            text=" ".join(word.text for word in words),
            words=tuple(words),
            languages=(LanguageSpan(0, chunk.duration_ms, language if isinstance(language, str) else None),),
        )


def _load(model: str, device: str, compute_type: str, cpu_threads: int) -> Any:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ProviderError(NAME, "faster-whisper is not installed (uv sync --extra whisper)", retryable=False) from exc
    log.info("loading Whisper model", extra={"model": model, "device": device, "compute_type": compute_type})
    try:
        return WhisperModel(model, device=device, compute_type=compute_type, cpu_threads=cpu_threads)
    except (RuntimeError, ValueError, OSError) as exc:
        reason = f"model {model!r} could not be loaded ({type(exc).__name__})"
        raise ProviderError(NAME, reason, retryable=False) from exc
