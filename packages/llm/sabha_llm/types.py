"""The gateway's request and result shapes, shared by every provider adapter (plan task P5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]
Tier = Literal["small", "mid"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Usage:
    """Token counts as the provider reported them."""

    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0  # part of tokens_in served from the provider's prompt cache
    cache_write_tokens: int = 0  # part of tokens_in written to the prompt cache (billed at its own price)

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    model: str  # the provider's own model name, e.g. "o3-mini"
    messages: tuple[Message, ...]
    json_schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None  # sent only if the model is known to accept it (catalog)
    reasoning_effort: str | None = None  # likewise


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str
    usage: Usage
    model_id: str  # as the provider names the model that answered


@dataclass(frozen=True, slots=True)
class CompletionResult:
    task: str
    model: str  # "<provider>:<model>" that answered
    text: str
    json: Any | None
    usage: Usage
    cost_usd: float | None  # None when the model has no published price in the catalog (golden rule 6)
    latency_ms: int
    prompt_hash: str
    fallback_reason: str | None = None
    attempts: list[str] = field(default_factory=list)  # "<model>: <error>" for every failed attempt before this one
