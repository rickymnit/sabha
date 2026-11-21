"""Deepgram Nova-3 speech-to-text with Hindi-English code-switching (docs/adr/0012-more-asr-providers.md).

Request (https://developers.deepgram.com/docs/multilingual-code-switching): POST {base_url}/v1/listen with the
chunk's WAV as the body, `Authorization: Token <DEEPGRAM_API_KEY>`, and query `model=nova-3`, `language=multi`
(code-switching: each word in the language it was spoken), `language_hint=hi` and `language_hint=en` (bias, not a
restriction), `punctuate=true`. Smart formatting is off so numbers stay as spoken.

Response: `results.channels[0].alternatives[0].words[]`, each {word, punctuated_word, start, end (seconds),
confidence, language}. Words are timed, so word_timing is "word"; consecutive words in one language become one
LanguageSpan.

Errors: see sabha_asr.providers._http (Deepgram's code is `err_code`). A bad key or no credit is never retried.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeGuard

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError
from sabha_asr.providers import _http
from sabha_asr.words import Word

NAME = "deepgram"
DEFAULT_MODEL = "nova-3"
DEFAULT_BASE_URL = "https://api.deepgram.com"
MAX_CHUNK_MS = 29_500  # the pipeline's chunks stay under 30 s for every provider
DEFAULT_TIMEOUT_S = 90.0
EXPECTED_LANGUAGES = ("hi", "en")
_NOT_RETRYABLE = frozenset({"INVALID_AUTH", "INSUFFICIENT_PERMISSIONS", "ASR_PAYMENT_REQUIRED"})

log = logging.getLogger("sabha.asr.deepgram")


class DeepgramProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        language: str = "unknown",
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("a Deepgram API key is required")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._url = f"{base_url.rstrip('/')}/v1/listen"
        self._client = client or httpx.Client(timeout=timeout_s, follow_redirects=False)
        self._sleep = sleep

    @property
    def name(self) -> str:
        return NAME

    @property
    def model_id(self) -> str:
        return f"{NAME}/{self._model}"

    @property
    def word_timing(self) -> WordTiming:
        return "word"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def close(self) -> None:
        self._client.close()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        return [self._transcribe_one(chunk) for chunk in chunks]

    def params(self, chunk: AudioChunk) -> tuple[tuple[str, str], ...]:
        """Code-switching unless this chunk or ASR_LANGUAGE names one language ("hi-IN" is sent as "hi")."""
        terms = tuple(("keyterm", term) for term in chunk.hints)  # Nova-3 key term prompting (ADR 0019)
        query = (("model", self._model), ("punctuate", "true"), *terms)
        hint = (chunk.language or self._language).split("-")[0]
        if hint and hint != "unknown":
            return (*query, ("language", hint))
        return (*query, ("language", "multi"), *(("language_hint", code) for code in EXPECTED_LANGUAGES))

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        if chunk.duration_ms > MAX_CHUNK_MS:
            raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; the limit is {MAX_CHUNK_MS} ms")
        params = self.params(chunk)

        def request() -> httpx.Response:
            return self._client.post(self._url, params=params, content=chunk.wav,
                                     headers={"Authorization": f"Token {self._api_key}",
                                              "Content-Type": "audio/wav"})  # fmt: skip

        response = _http.send(NAME, request, not_retryable=_NOT_RETRYABLE, sleep=self._sleep, log=log,
                              chunk_id=chunk.chunk_id)  # fmt: skip
        if response.status_code != 200:
            raise _http.error_for(NAME, response, _NOT_RETRYABLE)
        return parse(chunk, _http.json_body(NAME, response))


def parse(chunk: AudioChunk, body: Any) -> ChunkResult:
    try:
        raw = body["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(NAME, "response has no words", retryable=False) from exc
    if not isinstance(raw, list):
        raise ProviderError(NAME, "words is not a list", retryable=False)
    words: list[Word] = []
    spans: list[LanguageSpan] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProviderError(NAME, "a word is not an object", retryable=False)
        text = item.get("punctuated_word") or item.get("word")
        start_s, end_s = item.get("start"), item.get("end")
        if not isinstance(text, str) or not (_is_number(start_s) and _is_number(end_s)):
            raise ProviderError(NAME, "a word has no text or times", retryable=False)
        if not text.strip():
            continue
        start = min(max(round(start_s * 1000), 0), chunk.duration_ms)
        end = min(max(round(end_s * 1000), start), chunk.duration_ms)
        confidence = item.get("confidence")
        words.append(Word(text.strip(), start, end, float(confidence) if _is_number(confidence) else None))
        language = item.get("language") if isinstance(item.get("language"), str) else None
        if spans and spans[-1].language == language:
            spans[-1] = LanguageSpan(spans[-1].start_ms, end, language)
        else:
            spans.append(LanguageSpan(start, end, language))
    if spans:  # the spans tile the whole chunk, as every provider's do
        spans[0] = LanguageSpan(0, spans[0].end_ms, spans[0].language)
        spans[-1] = LanguageSpan(spans[-1].start_ms, chunk.duration_ms, spans[-1].language)
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        text=" ".join(word.text for word in words),
        words=tuple(words),
        languages=tuple(spans) or (LanguageSpan(0, chunk.duration_ms, None),),
    )


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)
