"""Google Gemini as speech-to-text, writing Hindi in Devanagari and English words in Latin letters (owner, 2026-11-16;
docs/adr/0012-more-asr-providers.md).

Request (https://ai.google.dev/gemini-api/docs/audio): POST {base_url}/v1beta/models/{model}:generateContent,
header `x-goog-api-key`, JSON body with the chunk's WAV as `inline_data` and INSTRUCTION, temperature 0 and a JSON
answer {"text": ...}. Gemini is a general model, not a speech recogniser, so INSTRUCTION forbids translating,
summarising and completing sentences, and asks for an empty text when nobody speaks. There are no word times: the
text is spread across the chunk (word_timing "approximate", like Sarvam's phrases).

Billing is by tokens: the answer's `usageMetadata` (prompt tokens in; answer and thinking tokens out, thinking billed
as output) is kept on the chunk's result (`ChunkResult.usage`), summed over both attempts when the guard below asks
again, since both were billed. sabha_asr.pricing.token_cost_inr turns it into money.

Guard: an answer with more than MAX_WORDS_PER_S words per second of audio cannot have been spoken (fast speech is
about 3 to 4); it is asked once more, and a second such answer fails the chunk rather than put invented words in a
transcript (golden rule 5).

Models (https://aistudio.google.com/docs/pricing, checked 2026-11-16 and 2026-11-18): `gemini-3.8-flash` (default),
`gemini-3.5-flash-lite` and `gemini-2.5-flash` (owner 2026-11-18). Audio is 25 tokens per second.

Thinking: 2.5 Flash is asked to think not at all (THINKING; thinking is billed as output and was 88% of a 3.8 Flash
call's cost on 2026-11-18). The other models keep Google's default for now.

Model check: Google retires 2.5 Flash and, from 2026-12-01, answers its requests with 3.5 Flash-Lite. An answer whose
`modelVersion` is not the model asked for is refused (golden rule 7: never a silent swap of model).

Errors: see sabha_asr.providers._http (Google's code is `error.status`). A bad key or a blocked answer is never retried.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from sabha_asr.assembly import WordTiming
from sabha_asr.provider import AudioChunk, ChunkResult, LanguageSpan, ProviderError, TokenUsage, spread_words
from sabha_asr.providers import _http

NAME = "gemini"
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
MAX_CHUNK_MS = 29_500  # the pipeline's chunks stay under 30 s for every provider
DEFAULT_TIMEOUT_S = 90.0
MAX_WORDS_PER_S = 6.0
THINKING: dict[str, dict[str, Any]] = {"gemini-2.5-flash": {"thinkingBudget": 0}}
"""Per model, the thinkingConfig sent (module docstring); a model not listed gets Google's default."""
_NOT_RETRYABLE = frozenset({"PERMISSION_DENIED", "UNAUTHENTICATED", "INVALID_ARGUMENT", "FAILED_PRECONDITION"})

INSTRUCTION = """Transcribe this audio exactly as it is spoken. It is part of a phone call or meeting in India, in \
Hindi, English, or both mixed together.

Rules:
- Write Hindi words in Devanagari script. Write English words in English (Latin) letters, also when they are spoken \
inside a Hindi sentence.
- Never translate. Every word stays in the language it was spoken in.
- Never summarise, correct grammar, complete sentences or add words that were not spoken. Keep repeated words and \
fillers.
- Write numbers the way they are spoken.
- Never use Urdu, Bengali or any other script.
- If nobody speaks, answer with an empty text."""

ANSWER_SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}

log = logging.getLogger("sabha.asr.gemini")


class GeminiProvider:
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
            raise ValueError("a Gemini API key is required")
        self._api_key = api_key
        self._model = model
        self._language = language  # unused: the instruction covers Hindi, English and both
        self._url = f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent"
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
        audio = base64.b64encode(chunk.wav).decode("ascii")
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"inline_data": {"mime_type": "audio/wav", "data": audio}}, {"text": INSTRUCTION}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": ANSWER_SCHEMA,
                **({"thinkingConfig": THINKING[self._model]} if self._model in THINKING else {}),
            },
        }

    def _transcribe_one(self, chunk: AudioChunk) -> ChunkResult:
        if chunk.duration_ms > MAX_CHUNK_MS:
            raise ValueError(f"chunk {chunk.chunk_id!r} is {chunk.duration_ms} ms; the limit is {MAX_CHUNK_MS} ms")
        usage: TokenUsage | None = None
        for attempt in (1, 2):
            text, billed = self._ask(chunk)
            usage = billed if usage is None else (None if billed is None else usage + billed)
            if plausible(text, chunk.duration_ms):
                break
            log.warning("answer has more words than the audio could hold", extra={"chunk_id": chunk.chunk_id,
                                                                                    "attempt": attempt})  # fmt: skip
        else:
            raise ProviderError(NAME, "answer has more words than the audio could hold", retryable=False)
        words = spread_words(text, 0, chunk.duration_ms)
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            text=" ".join(word.text for word in words),
            words=tuple(words),
            languages=(LanguageSpan(0, chunk.duration_ms, None),),
            usage=usage,
        )

    def _ask(self, chunk: AudioChunk) -> tuple[str, TokenUsage | None]:
        body = self.body(chunk)

        def request() -> httpx.Response:
            return self._client.post(self._url, headers={"x-goog-api-key": self._api_key}, json=body)

        response = _http.send(NAME, request, not_retryable=_NOT_RETRYABLE, sleep=self._sleep, log=log,
                              chunk_id=chunk.chunk_id)  # fmt: skip
        if response.status_code != 200:
            raise _http.error_for(NAME, response, _NOT_RETRYABLE)
        answer = _http.json_body(NAME, response)
        version = answer.get("modelVersion") if isinstance(answer, dict) else None
        if isinstance(version, str) and not version.startswith(self._model):
            raise ProviderError(NAME, f"answered by {version}, not {self._model}", retryable=False)
        return parse(answer), usage_of(answer)


def usage_of(body: Any) -> TokenUsage | None:
    """The tokens an answer was billed for, from `usageMetadata`; None when the answer does not say."""
    meta = body.get("usageMetadata") if isinstance(body, dict) else None
    if not isinstance(meta, dict) or not isinstance(meta.get("promptTokenCount"), int):
        return None
    answer, thinking = meta.get("candidatesTokenCount", 0), meta.get("thoughtsTokenCount", 0)
    if not isinstance(answer, int) or not isinstance(thinking, int):
        return None
    return TokenUsage(meta["promptTokenCount"], answer + thinking, thinking)


def parse(body: Any) -> str:
    """The transcript text of a generateContent answer. A blocked or cut-off answer is an error, never a transcript."""
    try:
        candidate = body["candidates"][0]
    except (KeyError, IndexError, TypeError) as exc:
        blocked = body.get("promptFeedback", {}).get("blockReason") if isinstance(body, dict) else None
        raise ProviderError(NAME, f"no answer ({blocked or 'empty'})", retryable=False) from exc
    reason = candidate.get("finishReason") if isinstance(candidate, dict) else None
    if reason not in (None, "STOP"):
        raise ProviderError(NAME, f"answer stopped early ({reason})", retryable=False)
    try:
        parts = candidate["content"]["parts"]
        raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and not part.get("thought"))
        text = json.loads(raw)["text"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(NAME, "answer is not the expected JSON", retryable=False) from exc
    if not isinstance(text, str):
        raise ProviderError(NAME, "answer text is not a string", retryable=False)
    return " ".join(text.split())


def plausible(text: str, duration_ms: int) -> bool:
    """At most MAX_WORDS_PER_S words per second (a chunk shorter than 1 s counts as 1 s)."""
    return len(text.split()) <= MAX_WORDS_PER_S * max(duration_ms, 1000) / 1000
