"""OpenAI speech-to-text over its transcriptions endpoint (docs/adr/0012-more-asr-providers.md).

Request: POST {base_url}/audio/transcriptions, multipart form, `Authorization: Bearer`. Fields: `file` (the chunk's
WAV) and `model`. One request per chunk; chunks are at most 30 s (well under OpenAI's 25 MB file limit).

Models (https://developers.openai.com/api/docs/guides/speech-to-text):
- `gpt-transcribe` (default): OpenAI's recommended model for recorded speech. Answers {text, languages}; no word
  times, so the text is spread across the chunk (word_timing "approximate", like Sarvam's phrases). A language hint
  is sent as `languages` (this model takes a list, not the singular `language`).
- `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`: {text}; also approximate. Deprecated by OpenAI (shut down
  2027-02-26). A hint is sent as `language`.
- `whisper-1`: asked for `verbose_json` with word timestamps, so word_timing is "word". Deprecated as above.

A BCP-47 hint ("hi-IN") is sent as its language part ("hi").

Script (owner, 2026-11-13: transcripts only in English, Hindi and Hinglish, never Urdu, Bengali or other scripts):
left to detect the language itself, the model sometimes writes Hindi speech in Urdu or Bengali script. So with
ASR_LANGUAGE "unknown", gpt-transcribe is told to expect Hindi and English (`languages` hi, en) and the older models
are told Hindi (`language` hi). No sample `prompt` is sent: on a real support call gpt-4o-mini-transcribe copied a
sample sentence into 12 of 44 pieces, which would put words nobody said in the transcript. The transcribe stage
still asks again, in Hindi, any chunk that comes back in another script (sabha_workers.stages.transcribe).

Errors: see sabha_asr.providers._http. `insufficient_quota` and `invalid_api_key` are never retried.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeGuard

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError, spread_words
from sabha_asr.providers import _http
from sabha_asr.words import Word

NAME = "openai"
DEFAULT_MODEL = "gpt-transcribe"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
MAX_CHUNK_MS = 29_500  # the pipeline's chunks stay under 30 s for every provider
DEFAULT_TIMEOUT_S = 90.0
WORD_TIMESTAMP_MODELS = frozenset({"whisper-1"})
_LIST_LANGUAGE_MODELS = frozenset({"gpt-transcribe"})
_NOT_RETRYABLE = frozenset({"insufficient_quota", "invalid_api_key"})
EXPECTED_LANGUAGES = ("hi", "en")  # gpt-transcribe, when no hint is configured
DEFAULT_HINT = "hi"  # the older models, which take one language, when no hint is configured

log = logging.getLogger("sabha.asr.openai")


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        language: str = "unknown",
        base_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("an OpenAI API key is required")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/audio/transcriptions"
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
        return "word" if self._model in WORD_TIMESTAMP_MODELS else "approximate"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def close(self) -> None:
        self._client.close()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        return [self._transcribe_one(chunk) for chunk in chunks]

    def _form(self, chunk: AudioChunk) -> dict[str, str | list[str]]:
        form: dict[str, str | list[str]] = {"model": self._model}
        hint = (chunk.language or self._language).split("-")[0]
        if self._model in _LIST_LANGUAGE_MODELS:
            form["languages[]"] = [hint] if hint and hint != "unknown" else list(EXPECTED_LANGUAGES)
        else:
            form["language"] = hint if hint and hint != "unknown" else DEFAULT_HINT
        if self._model in WORD_TIMESTAMP_MODELS:
            form |= {"response_format": "verbose_json", "timestamp_granularities[]": ["word"]}
        return form

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        if chunk.duration_ms > MAX_CHUNK_MS:
            raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; the limit is {MAX_CHUNK_MS} ms")
        form = self._form(chunk)

        def request() -> httpx.Response:
            return self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=form,
                files={"file": (f"{chunk.chunk_id}.wav", chunk.wav, "audio/wav")},
            )

        response = _http.send(NAME, request, not_retryable=_NOT_RETRYABLE, sleep=self._sleep, log=log,
                              chunk_id=chunk.chunk_id)  # fmt: skip
        if response.status_code != 200:
            raise _http.error_for(NAME, response, _NOT_RETRYABLE)
        return parse(chunk, _http.json_body(NAME, response))


def parse(chunk: AudioChunk, body: Any) -> ChunkResult:
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise ProviderError(NAME, "response has no text", retryable=False)
    words = _timed_words(chunk, body["words"]) if body.get("words") else []
    if not words:
        words = spread_words(body["text"], 0, chunk.duration_ms)
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        text=" ".join(word.text for word in words),
        words=tuple(words),
        languages=(LanguageSpan(0, chunk.duration_ms, _language(body)),),
    )


def _language(body: dict[str, Any]) -> str | None:
    languages = body.get("languages")
    if isinstance(languages, list) and languages:
        first = languages[0]
        code = first.get("language") or first.get("code") if isinstance(first, dict) else first
        return code if isinstance(code, str) and code else None
    language = body.get("language")
    return language if isinstance(language, str) and language else None


def _timed_words(chunk: AudioChunk, raw: Any) -> list[Word]:
    """whisper-1's {word, start, end} (seconds), clamped to the chunk."""
    if not isinstance(raw, list):
        raise ProviderError(NAME, "words is not a list", retryable=False)
    words = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("word"), str):
            raise ProviderError(NAME, "a word has no text", retryable=False)
        start_s, end_s = item.get("start"), item.get("end")
        if not (_is_number(start_s) and _is_number(end_s)):
            raise ProviderError(NAME, "a word has no times", retryable=False)
        text = item["word"].strip()
        if not text:
            continue
        start = min(max(round(start_s * 1000), 0), chunk.duration_ms)
        end = min(max(round(end_s * 1000), start), chunk.duration_ms)
        words.append(Word(text, start, end, None))
    return words


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)
