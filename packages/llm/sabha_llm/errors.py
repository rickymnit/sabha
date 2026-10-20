"""Errors the gateway raises. Reasons are safe to log: they never contain prompt or response text."""

from __future__ import annotations


class LlmError(Exception):
    """Base class for every gateway error."""


class LlmConfigError(LlmError):
    """The settings name an unknown task, provider or model."""


class ProviderError(LlmError):
    """A provider call failed. `retryable` is True for rate limits, server errors and timeouts only."""

    def __init__(self, provider: str, reason: str, *, retryable: bool, status: int | None = None) -> None:
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason
        self.retryable = retryable
        self.status = status


class BudgetExceededError(LlmError):
    """A tenant's or the global daily token budget is used up. Not retried: it resets at 00:00 UTC."""


class BudgetUnavailableError(LlmError):
    """The budget counters (Redis) cannot be read. Calls stop rather than spend without a limit."""


class InvalidJsonError(LlmError):
    """The answer did not match the JSON schema, even after one repair attempt."""
