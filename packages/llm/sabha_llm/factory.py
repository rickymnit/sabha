"""Build the gateway from settings (workers call this once per process)."""

from __future__ import annotations

from typing import Any

from pymongo.database import Database
from redis import Redis

from sabha_core.settings import Settings
from sabha_llm.budget import TokenBudget
from sabha_llm.errors import LlmConfigError
from sabha_llm.gateway import Gateway, Provider
from sabha_llm.providers.openai import OpenAIProvider
from sabha_llm.usage import MongoUsage


def build_gateway(settings: Settings, *, database: Database[dict[str, Any]], redis: Redis | None) -> Gateway:
    providers: dict[str, Provider] = {}
    if settings.openai_api_key is not None:
        providers["openai"] = OpenAIProvider(
            settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            timeout_s=settings.llm_timeout_s,
        )
    if not providers:
        raise LlmConfigError("no LLM provider is configured (set OPENAI_API_KEY)")
    return Gateway(
        providers=providers,
        models={"small": settings.llm_model_small, "mid": settings.llm_model_mid},
        fallbacks=settings.llm_fallbacks,
        max_retries=settings.llm_max_retries,
        budget=TokenBudget(
            redis,
            tenant_daily=settings.llm_tenant_daily_token_budget,
            global_daily=settings.llm_global_daily_token_budget,
        ),
        usage=MongoUsage(database),
    )
