"""Models and usage (owner's request, 2026-11-20): what this organisation used of each AI model, and the credit left
on the providers that report it.

Golden rule 6: every number is measured. Usage comes from the transcripts (speech-to-text minutes and their priced
cost, sabha_asr.pricing) and llm_calls (tokens and the gateway's priced cost). Credit left comes only from a
provider's own balance API (Deepgram); providers without one (OpenAI, Gemini, Sarvam, Groq) get a link to their
console instead of a number. Balances are for the whole API key, shared by every organisation on this server.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from sabha_core.models import LlmCall, Transcript
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings

ALLOWED = ("owner", "admin")
DAYS = 30
log = logging.getLogger("sabha.api.models_usage")

# Where each provider shows its balance and spend. No numbers here, only links.
CONSOLES: dict[str, tuple[str, str]] = {
    "openai": ("OpenAI", "https://platform.openai.com/settings/organization/billing/overview"),
    "gemini": ("Google Gemini", "https://aistudio.google.com/usage"),
    "sarvam": ("Sarvam AI", "https://dashboard.sarvam.ai"),
    "deepgram": ("Deepgram", "https://console.deepgram.com"),
    "groq": ("Groq", "https://console.groq.com/settings/billing"),
    "qwen": ("Alibaba Cloud", "https://bailian.console.alibabacloud.com"),
    "aws": ("AWS Transcribe", "https://console.aws.amazon.com/billing/home"),
}


class ModelUsage(BaseModel):
    kind: Literal["speech", "llm"]
    provider: str
    model: str
    runs: int  # transcripts or LLM calls
    minutes: float | None = None  # speech: audio sent
    tokens_in: int | None = None
    tokens_out: int | None = None
    inr: float | None  # None when any run has no price (a partial sum would understate)
    errors: int = 0


class DayUsage(BaseModel):
    day: str  # YYYY-MM-DD, UTC
    speech_inr: float
    llm_inr: float


class Balance(BaseModel):
    provider: str
    name: str
    console_url: str
    configured: bool
    amount: float | None = None  # only from the provider's balance API
    currency: str | None = None
    note: str | None = None


class ModelsUsageOut(BaseModel):
    since: datetime
    days: int
    usd_inr_rate: float | None
    total_inr: float | None
    speech_inr: float | None
    llm_inr: float | None
    models: list[ModelUsage]
    daily: list[DayUsage]
    balances: list[Balance]


def _provider(model_id: str) -> tuple[str, str]:
    for sep in ("/", ":"):
        if sep in model_id:
            p, m = model_id.split(sep, 1)
            return p, m
    return model_id, model_id


async def _deepgram_balance(settings: Settings) -> tuple[float | None, str | None, str | None]:
    key = settings.deepgram_api_key
    if key is None:
        return None, None, None
    headers = {"Authorization": f"Token {key.get_secret_value()}"}
    try:
        async with httpx.AsyncClient(base_url=settings.deepgram_base_url, headers=headers, timeout=8) as client:
            projects = (await client.get("/v1/projects")).raise_for_status().json().get("projects") or []
            total, currency = 0.0, None
            for project in projects:
                body = (await client.get(f"/v1/projects/{project['project_id']}/balances")).raise_for_status().json()
                for b in body.get("balances") or []:
                    total += float(b.get("amount") or 0)
                    currency = (b.get("units") or "usd").upper()
            return round(total, 2), currency or "USD", None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("deepgram balance unavailable", extra={"error": type(exc).__name__})
        return None, None, "Could not reach Deepgram just now."


KEYS = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "sarvam": "sarvam_api_key",
    "deepgram": "deepgram_api_key",
    "groq": "groq_api_key",
    "qwen": "dashscope_api_key",
}


def _configured(settings: Settings, provider: str) -> bool:
    attr = KEYS.get(provider)
    return attr is not None and getattr(settings, attr, None) is not None


async def summary(
    settings: Settings, transcripts: TenantRepo[Transcript], llm_calls: TenantRepo[LlmCall]
) -> ModelsUsageOut:
    now = datetime.now(UTC)
    since = (now - timedelta(days=DAYS - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rate = settings.usd_inr_rate
    window = {"created_at": {"$gte": since}}
    day = {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}

    speech_rows: list[dict[str, Any]] = await transcripts.aggregate([
        {"$match": {**window, "asr_model": {"$not": {"$regex": "^import:"}}}},
        {"$group": {"_id": "$asr_model", "runs": {"$sum": 1}, "ms": {"$sum": {"$ifNull": ["$asr_billed_ms", 0]}},
                    "inr": {"$sum": {"$ifNull": ["$asr_cost_inr", 0]}},
                    "unpriced": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$asr_cost_inr", None]}, None]}, 1, 0]}}}},
    ])  # fmt: skip
    llm_rows: list[dict[str, Any]] = await llm_calls.aggregate([
        {"$match": window},
        {"$group": {"_id": {"p": "$provider", "m": "$model"}, "runs": {"$sum": 1},
                    "tin": {"$sum": "$tokens_in"}, "tout": {"$sum": "$tokens_out"},
                    "usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
                    "unpriced": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$cost_usd", None]}, None]}, 1, 0]}},
                    "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}}}},
    ])  # fmt: skip
    speech_days = {r["_id"]: r["inr"] for r in await transcripts.aggregate([
        {"$match": window}, {"$group": {"_id": day, "inr": {"$sum": {"$ifNull": ["$asr_cost_inr", 0]}}}}])}  # fmt: skip
    llm_days = {r["_id"]: r["usd"] for r in await llm_calls.aggregate([
        {"$match": window}, {"$group": {"_id": day, "usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}}}}])}  # fmt: skip

    models: list[ModelUsage] = []
    for r in speech_rows:
        provider, model = _provider(str(r["_id"]))
        models.append(ModelUsage(kind="speech", provider=provider, model=model, runs=r["runs"],
                                 minutes=round(r["ms"] / 60_000, 1),
                                 inr=None if r["unpriced"] else round(r["inr"], 2)))  # fmt: skip
    for r in llm_rows:
        inr = None if r["unpriced"] or not rate else round(r["usd"] * rate, 2)
        models.append(ModelUsage(kind="llm", provider=str(r["_id"]["p"]), model=str(r["_id"]["m"]), runs=r["runs"],
                                 tokens_in=r["tin"], tokens_out=r["tout"], inr=inr, errors=r["errors"]))  # fmt: skip
    models.sort(key=lambda m: m.inr or 0, reverse=True)

    def part(kind: str) -> float | None:
        rows = [m for m in models if m.kind == kind]
        return None if any(m.inr is None for m in rows) else round(sum(m.inr or 0 for m in rows), 2)

    speech_inr, llm_inr = part("speech"), part("llm")
    daily = []
    for i in range(DAYS):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append(DayUsage(day=d, speech_inr=round(speech_days.get(d, 0), 2),
                              llm_inr=round(llm_days.get(d, 0) * (rate or 0), 2)))  # fmt: skip

    used = {m.provider for m in models}
    balances: list[Balance] = []
    for provider, (name, url) in CONSOLES.items():
        configured = _configured(settings, provider)
        if not configured and provider not in used:
            continue
        balance = Balance(provider=provider, name=name, console_url=url, configured=configured)
        if provider == "deepgram" and configured:
            balance.amount, balance.currency, balance.note = await _deepgram_balance(settings)
        balances.append(balance)

    return ModelsUsageOut(
        since=since, days=DAYS, usd_inr_rate=rate,
        total_inr=round(speech_inr + llm_inr, 2) if speech_inr is not None and llm_inr is not None else None,
        speech_inr=speech_inr, llm_inr=llm_inr, models=models, daily=daily, balances=balances,
    )  # fmt: skip
