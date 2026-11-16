"""Groq speech-to-text: OpenAI's Whisper models on Groq's servers (docs/adr/0012-more-asr-providers.md).

Groq serves OpenAI's transcription API at https://api.groq.com/openai/v1, so this is the OpenAI provider with Groq's
address and models (https://console.groq.com/docs/speech-to-text):
- `whisper-large-v3` (default): Whisper's largest model.
- `whisper-large-v3-turbo`: a smaller, faster and cheaper version of it.

Both are asked for `verbose_json` with word timestamps, so word_timing is "word". Both take one `language`, sent as
"hi" when no hint is configured, like OpenAI's older models (owner's rule: transcripts only in English, Hindi and
Hinglish). Groq bills at least 10 s per request; the pipeline's chunks are up to 30 s.

Groq's limits are per minute (requests and audio seconds; low on the free plan), and one call is about a hundred
chunks, so a rate limit is waited out longer than for OpenAI: up to RATE_LIMIT_RETRIES waits, the last ones 30 s.
"""

from __future__ import annotations

from sabha_asr.providers.openai import OpenAIProvider

NAME = "groq"
DEFAULT_MODEL = "whisper-large-v3"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAIProvider):
    NAME = NAME
    DEFAULT_MODEL = DEFAULT_MODEL
    DEFAULT_BASE_URL = DEFAULT_BASE_URL
    WORD_TIMESTAMP_MODELS = frozenset({"whisper-large-v3", "whisper-large-v3-turbo"})
    RATE_LIMIT_RETRIES = 8
