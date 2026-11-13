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

Currency = Literal["INR", "USD"]

_OPENAI = "https://developers.openai.com/api/docs/pricing (Transcription, estimated cost, checked 2026-11-13)"
_QWEN = ("https://www.alibabacloud.com/help/en/model-studio/qwen3-asr-flash (international, Singapore: "
         "0.000035 USD per second of audio, checked 2026-11-13)")  # fmt: skip
_AWS = ("AWS Price List API, Amazon Transcribe, Asia Pacific (Mumbai), TranscribeAudio: 0.0001 USD per second "
        "(publication 2026-09-11, checked 2026-11-13)")  # fmt: skip


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
