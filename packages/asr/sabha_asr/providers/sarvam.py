"""Sarvam AI speech-to-text over its synchronous REST API (ADR 0006).

Request: POST {base_url}/speech-to-text, multipart form, header `api-subscription-key`. Fields: `file` (the chunk's
WAV), `model`, `language_code` ("unknown" detects the language, including Hindi-English switching),
`with_timestamps=true`, and `mode=transcribe` for saaras:v3 (v4 has no mode). One request per chunk; the REST API
takes at most 30 s of audio, so MAX_CHUNK_MS stays just under it.

Response: `transcript`, `language_code` (or null), and `timestamps` = {words, start_time_seconds, end_time_seconds},
three parallel lists in which each "word" is a phrase, not a word. Each phrase is split into words with
`spread_words`, so word_timing is "approximate" and confidence is None (Sarvam gives none). Phrase times are
clamped to the chunk. Without timestamps, the whole transcript is spread across the chunk.

Errors, from Sarvam's error guide: 429 (rate limit, except `insufficient_quota_error`), 500 and 503 are retryable;
400, 403, 413, 422 and running out of credits are not. Network errors and timeouts are retryable. Reasons name the
status and Sarvam's error code only: never the key, audio or transcript text.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError, spread_words
from sabha_asr.words import Word

NAME = "sarvam"
DEFAULT_MODEL = "saaras:v4"
MAX_CHUNK_MS = 29_500  # the REST limit is 30 s; keep a margin for WAV header rounding
DEFAULT_TIMEOUT_S = 60.0
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_NOT_RETRYABLE_CODES = frozenset({"insufficient_quota_error", "invalid_api_key_error"})


class SarvamProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        language: str = "unknown",
        base_url: str = "https://api.sarvam.ai",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("a Sarvam API key is required")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._url = f"{base_url.rstrip('/')}/speech-to-text"
        self._client = client or httpx.Client(timeout=timeout_s, follow_redirects=False)

    @property
    def name(self) -> str:
        return NAME

    @property
    def model_id(self) -> str:
        return f"{NAME}/{self._model}"

    @property
    def word_timing(self) -> WordTiming:
        return "approximate"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def close(self) -> None:
        self._client.close()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        return [self._transcribe_one(chunk) for chunk in chunks]

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        if chunk.duration_ms > MAX_CHUNK_MS:
            raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; Sarvam's limit is {MAX_CHUNK_MS} ms")
        data = {"model": self._model, "language_code": self._language, "with_timestamps": "true"}
        if self._model == "saaras:v3":
            data["mode"] = "transcribe"
        try:
            response = self._client.post(
                self._url,
                headers={"api-subscription-key": self._api_key},
                data=data,
                files={"file": (f"{chunk.chunk_id}.wav", chunk.wav, "audio/wav")},
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(NAME, f"timed out ({type(exc).__name__})", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ProviderError(NAME, f"network error ({type(exc).__name__})", retryable=True) from exc
        if response.status_code != 200:
            raise _http_error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(NAME, "response is not JSON", retryable=False) from exc
        return _parse(chunk, body)


def _http_error(response: httpx.Response) -> ProviderError:
    code = "unknown"
    try:
        error = response.json().get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            code = error["code"]
    except (ValueError, AttributeError):
        pass
    retryable = response.status_code in _RETRYABLE_STATUSES and code not in _NOT_RETRYABLE_CODES
    return ProviderError(NAME, f"HTTP {response.status_code} {code}", retryable=retryable)


def _parse(chunk: AudioChunk, body: Any) -> ChunkResult:
    if not isinstance(body, dict) or not isinstance(body.get("transcript"), str):
        raise ProviderError(NAME, "response has no transcript", retryable=False)
    language = body.get("language_code")
    if language is not None and not isinstance(language, str):
        raise ProviderError(NAME, "language_code is not a string", retryable=False)
    words = _words(chunk, body["transcript"], body.get("timestamps"))
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        text=" ".join(word.text for word in words),
        words=tuple(words),
        languages=(LanguageSpan(0, chunk.duration_ms, language),),
    )


def _words(chunk: AudioChunk, transcript: str, timestamps: Any) -> list[Word]:
    if not timestamps:
        return spread_words(transcript, 0, chunk.duration_ms)
    if not isinstance(timestamps, dict):
        raise ProviderError(NAME, "timestamps is not an object", retryable=False)
    phrases, starts, ends = (timestamps.get(k) for k in ("words", "start_time_seconds", "end_time_seconds"))
    if not (isinstance(phrases, list) and isinstance(starts, list) and isinstance(ends, list)):
        raise ProviderError(NAME, "timestamps lists are missing", retryable=False)
    if not len(phrases) == len(starts) == len(ends):
        raise ProviderError(NAME, "timestamps lists differ in length", retryable=False)
    timed = []
    for phrase, start_s, end_s in zip(phrases, starts, ends, strict=True):
        if not isinstance(phrase, str) or not all(_is_number(v) for v in (start_s, end_s)):
            raise ProviderError(NAME, "timestamps hold a value of the wrong type", retryable=False)
        start = min(max(round(start_s * 1000), 0), chunk.duration_ms)
        end = min(max(round(end_s * 1000), start), chunk.duration_ms)
        timed.append((start, end, phrase))
    timed.sort(key=lambda item: (item[0], item[1]))
    return [word for start, end, phrase in timed for word in spread_words(phrase, start, end)]


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
