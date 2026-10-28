"""Published speech-to-text prices, for cost reporting (golden rule 6: a price comes only from the provider's own
published figure, with its source and the date it was checked; a model without one costs None, never a guess).

Billing is by audio duration (Sarvam: "billed by audio duration"); the cost of a request is its audio minutes times
the per-minute price, unrounded, because the provider publishes no rounding or minimum.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AsrPrice:
    inr_per_minute: float
    source: str


PRICES: dict[str, AsrPrice] = {
    # Speech to Text, real-time and batch, pay as you go. Lower on the Pro/Growth/Business plans (0.45/0.41/0.38).
    "sarvam/saaras:v4": AsrPrice(
        0.49, "https://www.sarvam.ai/api-pricing (Speech to Text, pay as you go, checked 2026-10-28)"
    ),
}


def price_for(model_id: str) -> AsrPrice | None:
    return PRICES.get(model_id)


def cost_inr(model_id: str, audio_ms: int) -> float | None:
    """What sending `audio_ms` of audio to `model_id` costs in rupees, or None without a published price."""
    price = price_for(model_id)
    return None if price is None else price.inr_per_minute * audio_ms / 60_000
