"""Qwen speech recognition (Qwen3-ASR-Flash) on Alibaba Cloud Model Studio (docs/adr/0012-more-asr-providers.md).

Request (https://www.alibabacloud.com/help/en/model-studio/qwen-asr-api-reference, OpenAI-compatible mode):
POST {base_url}/chat/completions, `Authorization: Bearer <DASHSCOPE_API_KEY>`, JSON body

    {"model": "qwen3-asr-flash", "stream": false,
     "messages": [{"role": "user", "content": [{"type": "input_audio",
                                                "input_audio": {"data": "data:audio/wav;base64,..."}}]}],
     "asr_options": {"enable_itn": false, "language": "hi"}}

`asr_options.language` takes one language and only when it is known; a BCP-47 hint ("hi-IN") is sent as "hi", and
"unknown" sends none (mixed Hindi-English is left to the model). The default base URL is the international
(Singapore) endpoint. Limits: 10 MB per request (a 30 s chunk is about 1.3 MB as base64) and 5 minutes of audio.

Response: the text is `choices[0].message.content`; the language is in `choices[0].message.annotations[]` (the one
with type "audio_info"). Qwen3-ASR-Flash returns no timestamps in this mode, so the text is spread across the chunk
(word_timing "approximate", like Sarvam's phrases).

Errors: see sabha_asr.providers._http. A bad key or an account in arrears is never retried.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError, spread_words
from sabha_asr.providers import _http

NAME = "qwen"
DEFAULT_MODEL = "qwen3-asr-flash"
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MAX_CHUNK_MS = 29_500  # the pipeline's chunks stay under 30 s for every provider
DEFAULT_TIMEOUT_S = 90.0
_NOT_RETRYABLE = frozenset({"invalid_api_key", "InvalidApiKey", "Arrearage", "insufficient_quota", "AccessDenied"})

log = logging.getLogger("sabha.asr.qwen")


class QwenProvider:
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
            raise ValueError("a DashScope API key is required")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._url = f"{base_url.rstrip('/')}/chat/completions"
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
        return "approximate"

    @property
    def max_chunk_ms(self) -> int:
        return MAX_CHUNK_MS

    def close(self) -> None:
        self._client.close()

    def transcribe(self, chunks: Sequence[AudioChunk]) -> list[ChunkResult]:
        return [self._transcribe_one(chunk) for chunk in chunks]

    def body(self, chunk: AudioChunk) -> dict[str, Any]:
        audio = "data:audio/wav;base64," + base64.b64encode(chunk.wav).decode("ascii")
        options: dict[str, Any] = {"enable_itn": False}
        hint = (chunk.language or self._language).split("-")[0]
        if hint and hint != "unknown":
            options["language"] = hint
        return {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": audio}}]}],
            "asr_options": options,
        }

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        if chunk.duration_ms > MAX_CHUNK_MS:
            raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; the limit is {MAX_CHUNK_MS} ms")
        body = self.body(chunk)

        def request() -> httpx.Response:
            return self._client.post(self._url, headers={"Authorization": f"Bearer {self._api_key}"}, json=body)

        response = _http.send(NAME, request, not_retryable=_NOT_RETRYABLE, sleep=self._sleep, log=log,
                              chunk_id=chunk.chunk_id)  # fmt: skip
        if response.status_code != 200:
            raise _http.error_for(NAME, response, _NOT_RETRYABLE)
        return parse(chunk, _http.json_body(NAME, response))


def parse(chunk: AudioChunk, body: Any) -> ChunkResult:
    try:
        message = body["choices"][0]["message"]
        text = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(NAME, "response has no message", retryable=False) from exc
    if isinstance(text, list):  # some compatible-mode answers give content parts
        text = " ".join(part.get("text", "") for part in text if isinstance(part, dict))
    if not isinstance(text, str):
        raise ProviderError(NAME, "message content is not text", retryable=False)
    words = spread_words(text, 0, chunk.duration_ms)
    return ChunkResult(
        chunk_id=chunk.chunk_id,
        text=" ".join(word.text for word in words),
        words=tuple(words),
        languages=(LanguageSpan(0, chunk.duration_ms, _language(message)),),
    )


def _language(message: Any) -> str | None:
    annotations = message.get("annotations") if isinstance(message, dict) else None
    for note in annotations if isinstance(annotations, list) else []:
        language = note.get("language") if isinstance(note, dict) else None
        if isinstance(language, str) and language and language != "none":
            return language
    return None
