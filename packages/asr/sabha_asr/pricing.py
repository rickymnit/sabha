"""Published speech-to-text prices, for cost reporting (golden rule 6: a price comes only from the provider's own
published figure, with its source and the date it was checked; a model without one costs None, never a guess).

Every provider here bills by audio duration; the cost of a request is its audio minutes times the per-minute price,
unrounded (Sarvam and OpenAI publish no rounding or minimum; AWS bills per second with no minimum; Alibaba prices
per second). A price is kept in the currency it is published in. Rupees for a dollar price need the configured
exchange rate (USD_INR_RATE); without one the rupee cost is None, never converted at a guessed rate.

A self-hosted model (provider "whisper") has no per-minute price: its cost is the machine it runs on, which is not
counted here, so it is None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sabha_asr.provider import TokenUsage

Currency = Literal["INR", "USD"]

_OPENAI = "https://developers.openai.com/api/docs/pricing (Transcription, estimated cost, checked 2026-11-13)"
_QWEN = ("https://www.alibabacloud.com/help/en/model-studio/qwen3-asr-flash (international, Singapore: "
         "0.000035 USD per second of audio, checked 2026-11-13)")  # fmt: skip
_AWS = ("AWS Price List API, Amazon Transcribe, Asia Pacific (Mumbai), TranscribeAudio: 0.0001 USD per second "
        "(publication 2026-09-11, checked 2026-11-13)")  # fmt: skip

_GROQ = ("https://console.groq.com/docs/speech-to-text (whisper-large-v3 0.111 USD, whisper-large-v3-turbo 0.04 USD "
         "per audio hour; minimum 10 s billed per request, not counted here; checked 2026-11-16)")  # fmt: skip

_DEEPGRAM = ("https://deepgram.com/pricing (Nova-3 pre-recorded, pay as you go: multilingual 0.0052 USD per minute, "
             "billed per second, no minimum; checked 2026-11-16)")  # fmt: skip

# Gemini bills tokens: audio is 25 tokens per second (1,500 per minute). PRICES holds the audio only (a lower bound,
# for estimates before anything is sent); TOKEN_PRICES prices what a call was actually billed, output included.
_GEMINI = ("https://aistudio.google.com/docs/pricing (paid standard, checked 2026-11-16: gemini-3.8-flash input 0.75 "
           "USD per 1M tokens until 2026-12-31, then 1.50; gemini-3.5-flash-lite audio input 0.30 USD per 1M; "
           "25 audio tokens per second; output tokens not counted)")  # fmt: skip


_GEMINI_TOKENS = (
    "https://aistudio.google.com/docs/pricing (paid standard, checked 2026-11-18: gemini-3.8-flash input 0.75 and "
    "output 3.75 USD per 1M tokens through 2026-12-31, then 1.50 and 7.50; gemini-3.5-flash-lite input 0.30 and "
    "output 2.50; gemini-2.5-flash (deprecated, routed to 3.5-flash-lite from 2026-12-01) audio input 1.00 and output "
    "2.50; gemini-2.5-flash-lite audio input 0.30 and output 0.40; gemini-3.1-flash-lite audio input 0.50 and "
    "output 1.50, shutdown 2027-05-07; output includes thinking "
    "tokens)"
)


@dataclass(frozen=True, slots=True)
class TokenPrice:
    """Dollars per million tokens in and out (thinking billed as output)."""

    input_per_million: float
    output_per_million: float
    currency: Currency
    source: str

    def cost(self, usage: TokenUsage) -> float:
        return (usage.input_tokens * self.input_per_million + usage.output_tokens * self.output_per_million) / 1e6


TOKEN_PRICES: dict[str, TokenPrice] = {
    "gemini/gemini-3.8-flash": TokenPrice(0.75, 3.75, "USD", _GEMINI_TOKENS),  # 1.50 and 7.50 from 2027-01-01
    "gemini/gemini-3.5-flash-lite": TokenPrice(0.30, 2.50, "USD", _GEMINI_TOKENS),
    # Audio in costs 1.00 (text 0.30); all input is priced as audio, so a little high, never low.
    "gemini/gemini-2.5-flash": TokenPrice(1.00, 2.50, "USD", _GEMINI_TOKENS),
    "gemini/gemini-2.5-flash-lite": TokenPrice(0.30, 0.40, "USD", _GEMINI_TOKENS),  # audio in 0.30 (text 0.10)
    "gemini/gemini-3.1-flash-lite": TokenPrice(0.50, 1.50, "USD", _GEMINI_TOKENS),  # audio in 0.50 (text 0.25)
}


@dataclass(frozen=True, slots=True)
class AsrPrice:
    per_minute: float
    currency: Currency
    source: str

    def inr_per_minute(self, usd_inr_rate: float | None = None) -> float | None:
        """The price in rupees; a dollar price needs `usd_inr_rate` (None without it)."""
        if self.currency == "INR":
            return self.per_minute
        return None if usd_inr_rate is None else self.per_minute * usd_inr_rate


PRICES: dict[str, AsrPrice] = {
    # Speech to Text, real-time and batch, pay as you go. Lower on the Pro/Growth/Business plans (0.45/0.41/0.38).
    "sarvam/saaras:v4": AsrPrice(
        0.49, "INR", "https://www.sarvam.ai/api-pricing (Speech to Text, pay as you go, checked 2026-10-28)"
    ),
    "openai/gpt-transcribe": AsrPrice(0.0045, "USD", _OPENAI),
    # Deprecated by OpenAI; shut down on 2027-02-26.
    "openai/gpt-4o-mini-transcribe": AsrPrice(0.003, "USD", _OPENAI),
    "openai/gpt-4o-transcribe": AsrPrice(0.006, "USD", _OPENAI),
    "openai/whisper-1": AsrPrice(0.006, "USD", _OPENAI),
    "qwen/qwen3-asr-flash": AsrPrice(0.000035 * 60, "USD", _QWEN),
    "groq/whisper-large-v3": AsrPrice(0.111 / 60, "USD", _GROQ),
    "groq/whisper-large-v3-turbo": AsrPrice(0.04 / 60, "USD", _GROQ),
    "deepgram/nova-3": AsrPrice(0.0052, "USD", _DEEPGRAM),  # code-switching ("multi"), the way we call it
    "gemini/gemini-3.8-flash": AsrPrice(1500 * 0.75 / 1e6, "USD", _GEMINI),  # 1.50 per 1M from 2027-01-01
    "gemini/gemini-3.5-flash-lite": AsrPrice(1500 * 0.30 / 1e6, "USD", _GEMINI),
    "gemini/gemini-2.5-flash": AsrPrice(1500 * 1.00 / 1e6, "USD", _GEMINI),
    "gemini/gemini-3.1-flash-lite": AsrPrice(1500 * 0.50 / 1e6, "USD", _GEMINI),
    "gemini/gemini-2.5-flash-lite": AsrPrice(
        1500 * 0.30 / 1e6, "USD", _GEMINI
    ),  # audio only: an estimate before sending
    "aws/transcribe@ap-south-1": AsrPrice(0.0001 * 60, "USD", _AWS),  # other regions: not checked, so None
}


def price_for(model_id: str) -> AsrPrice | None:
    return PRICES.get(model_id)


def cost_inr(model_id: str, audio_ms: int, usd_inr_rate: float | None = None) -> float | None:
    """What sending `audio_ms` of audio to `model_id` costs in rupees, or None without a published price (or, for a
    dollar price, without `usd_inr_rate`)."""
    price = price_for(model_id)
    per_minute = None if price is None else price.inr_per_minute(usd_inr_rate)
    return None if per_minute is None else per_minute * audio_ms / 60_000


def token_cost_inr(model_id: str, usage: TokenUsage, usd_inr_rate: float | None = None) -> float | None:
    """What `usage` cost in rupees for a token-billed model, or None (not token-billed, or a dollar price without
    `usd_inr_rate`)."""
    price = TOKEN_PRICES.get(model_id)
    if price is None:
        return None
    native = price.cost(usage)
    if price.currency == "INR":
        return native
    return None if usd_inr_rate is None else native * usd_inr_rate
