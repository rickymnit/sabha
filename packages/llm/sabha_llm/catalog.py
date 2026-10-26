"""Models the gateway may call, with what they accept and their published prices (plan task P5.1).

Prices come only from docs/llm-providers.md, which records each provider's own published figure with its source
and the date checked (golden rule 6). A model without prices still works; its calls record cost as None.
`accepts_temperature` / `accepts_reasoning_effort` are True only when the provider's documentation says so; until
then the gateway does not send those parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

from sabha_llm.errors import LlmConfigError


@dataclass(frozen=True, slots=True)
class ModelSpec:
    provider: str
    name: str
    usd_per_m_input: float | None = None
    usd_per_m_cached_input: float | None = None
    usd_per_m_output: float | None = None
    # Writing input to the prompt cache, where the provider prices it separately; otherwise it costs as input.
    usd_per_m_cache_write: float | None = None
    price_source: str | None = None
    accepts_temperature: bool = False
    accepts_reasoning_effort: bool = False

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.name}"


CATALOG: dict[str, ModelSpec] = {
    spec.key: spec
    for spec in (
        ModelSpec(
            provider="openai",
            name="gpt-6-luna",
            usd_per_m_input=0.10,
            usd_per_m_cached_input=0.01,
            usd_per_m_output=0.50,
            usd_per_m_cache_write=0.125,
            price_source="https://developers.openai.com/api/docs/models/gpt-6-luna (checked 2026-10-24)",
            accepts_reasoning_effort=True,  # none, low, medium (default), high, xhigh, max (same page)
        ),
        # Shut down by OpenAI on 2026-10-23 (it now answers 404); kept so earlier calls' costs stay explained.
        ModelSpec(
            provider="openai",
            name="o3-mini",
            usd_per_m_input=1.10,
            usd_per_m_cached_input=0.55,
            usd_per_m_output=4.40,
            price_source="https://developers.openai.com/api/docs/models/o3-mini (checked 2026-10-19)",
        ),
        ModelSpec(provider="fake", name="fake-small"),
        ModelSpec(provider="fake", name="fake-mid"),
    )
}


def spec_for(key: str) -> ModelSpec:
    try:
        return CATALOG[key]
    except KeyError:
        raise LlmConfigError(f"unknown model {key!r}; known: {', '.join(sorted(CATALOG))}") from None


def cost_usd(
    spec: ModelSpec, tokens_in: int, cached_tokens: int, tokens_out: int, cache_write_tokens: int = 0
) -> float | None:
    """Cost from the published prices, or None if any needed price is missing. Cached and cache-write tokens are
    parts of `tokens_in`; cache writes cost as input unless the provider prices them separately."""
    cached_price = spec.usd_per_m_cached_input if cached_tokens else 0.0
    if spec.usd_per_m_input is None or spec.usd_per_m_output is None or cached_price is None:
        return None
    write_price = spec.usd_per_m_cache_write if spec.usd_per_m_cache_write is not None else spec.usd_per_m_input
    plain = max(0, tokens_in - cached_tokens - cache_write_tokens)
    total = (plain * spec.usd_per_m_input + cached_tokens * cached_price + cache_write_tokens * write_price
             + tokens_out * spec.usd_per_m_output)  # fmt: skip
    return round(total / 1_000_000, 8)
