"""The LLM gateway (plan task P5.1) with a scripted fake provider: routing, redaction, retries, explicit fallbacks,
JSON repair, usage records and cost. Budgets against real Redis are in test_budget.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from sabha_llm.budget import TokenBudget
from sabha_llm.catalog import CATALOG, ModelSpec, cost_usd
from sabha_llm.errors import InvalidJsonError, LlmConfigError, ProviderError
from sabha_llm.gateway import Gateway
from sabha_llm.providers.fake import FakeProvider
from sabha_llm.types import Message, Usage
from sabha_llm.usage import MemoryUsage

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5}},
    "required": ["score"],
    "additionalProperties": False,
}
NO_BUDGET = TokenBudget(None, tenant_daily=None, global_daily=None)
ASK = [Message("system", "You score lessons."), Message("user", "Teacher: aaj hum fractions padhenge.")]
RATE_LIMITED = ProviderError("fake", "HTTP 429 rate_limit_exceeded", retryable=True, status=429)
BAD_REQUEST = ProviderError("fake", "HTTP 400 invalid_request", retryable=False, status=400)


class Setup:
    def __init__(self, answers: list[Any], *, fallbacks: dict[str, list[str]] | None = None, retries: int = 3) -> None:
        self.provider = FakeProvider(answers)
        self.usage = MemoryUsage()
        self.sleeps: list[float] = []
        self.gateway = Gateway(
            providers={"fake": self.provider},
            models={"small": "fake:fake-small", "mid": "fake:fake-mid"},
            fallbacks=fallbacks,
            max_retries=retries,
            budget=NO_BUDGET,
            usage=self.usage,
            sleep=self.sleeps.append,
            jitter=lambda: 1.0,
        )

    def complete(self, task: str = "analysis.scoring", **kwargs: Any) -> Any:
        return self.gateway.complete(task=task, messages=ASK, tenant_id="tenant-a", recording_id="rec-1", **kwargs)


# --- Routing ---


def test_tasks_route_to_their_tier() -> None:
    setup = Setup(["ok", "ok"])
    assert setup.complete("analysis.scoring").model == "fake:fake-mid"
    assert setup.complete("roles.tiebreak").model == "fake:fake-small"
    assert [r.model for r in setup.provider.requests] == ["fake-mid", "fake-small"]


def test_an_unknown_task_is_a_configuration_error() -> None:
    with pytest.raises(LlmConfigError, match="unknown LLM task"):
        Setup(["ok"]).complete("summarise_everything")


def test_unknown_models_and_unconfigured_providers_fail_at_start_up() -> None:
    with pytest.raises(LlmConfigError, match="unknown model"):
        Gateway(providers={"fake": FakeProvider()}, models={"small": "fake:nope", "mid": "fake:fake-mid"},
                budget=NO_BUDGET, usage=MemoryUsage())  # fmt: skip
    with pytest.raises(LlmConfigError, match="not configured"):
        Gateway(providers={"fake": FakeProvider()}, models={"small": "openai:o3-mini", "mid": "fake:fake-mid"},
                budget=NO_BUDGET, usage=MemoryUsage())  # fmt: skip
    with pytest.raises(LlmConfigError, match="unknown tasks"):
        Setup(["ok"], fallbacks={"not_a_task": ["fake:fake-small"]})


# --- Redaction before anything leaves (golden rule 8) ---


def test_every_message_is_redacted_before_the_provider_sees_it() -> None:
    setup = Setup(["ok"])
    setup.gateway.complete(
        task="analysis.scoring",
        messages=[Message("user", "Call me on 98765 43210 or asha.rao@example.com, PAN ABCDE1234F.")],
        tenant_id="tenant-a",
    )
    sent = setup.provider.requests[0].messages[0].content
    assert "98765" not in sent and "asha.rao@example.com" not in sent
    assert "ABCDE1234F" not in sent  # pragma: allowlist secret  (a made-up PAN)
    assert "[PHONE_1]" in sent and "[EMAIL_1]" in sent and "[PAN_1]" in sent


# --- Retries only for retryable errors ---


def test_retryable_errors_are_retried_with_backoff() -> None:
    setup = Setup([RATE_LIMITED, RATE_LIMITED, "ok"])
    result = setup.complete()
    assert result.text == "ok" and result.fallback_reason is None
    assert setup.sleeps == [1.0, 2.0]  # full jitter at its maximum: 1 s, then 2 s
    assert [c.status for c in setup.usage.calls] == ["error", "error", "ok"]
    assert [c.attempt for c in setup.usage.calls] == [1, 2, 3]


def test_non_retryable_errors_are_not_retried() -> None:
    setup = Setup([BAD_REQUEST])
    with pytest.raises(ProviderError):
        setup.complete()
    assert len(setup.provider.requests) == 1 and setup.sleeps == []


def test_retries_stop_at_the_limit() -> None:
    setup = Setup([RATE_LIMITED] * 3, retries=2)
    with pytest.raises(ProviderError):
        setup.complete()
    assert len(setup.provider.requests) == 3


# --- Fallback only when configured, and logged (golden rule 7) ---


def test_without_a_configured_fallback_the_error_is_raised() -> None:
    setup = Setup([BAD_REQUEST, "never used"])
    with pytest.raises(ProviderError, match="every model failed"):
        setup.complete()
    assert len(setup.provider.requests) == 1


def test_a_configured_fallback_is_used_logged_and_recorded(caplog: pytest.LogCaptureFixture) -> None:
    setup = Setup([BAD_REQUEST, "ok"], fallbacks={"analysis.scoring": ["fake:fake-small"]})
    with caplog.at_level(logging.WARNING, logger="sabha.llm"):
        result = setup.complete()
    assert result.model == "fake:fake-small"
    assert result.fallback_reason == "fake:fake-mid: HTTP 400 invalid_request"
    (record,) = caplog.records
    assert record.__dict__["fallback_model"] == "fake:fake-small"
    assert setup.usage.calls[-1].fallback_reason == "fake:fake-mid: HTTP 400 invalid_request"


def test_fallbacks_are_per_task() -> None:
    setup = Setup([BAD_REQUEST], fallbacks={"analysis.synthesis": ["fake:fake-small"]})
    with pytest.raises(ProviderError):
        setup.complete("analysis.scoring")


# --- JSON ---


def test_valid_json_is_parsed() -> None:
    result = Setup(['{"score": 4}']).complete(json_schema=SCHEMA)
    assert result.json == {"score": 4}


def test_invalid_json_gets_one_repair_attempt() -> None:
    setup = Setup(['{"score": 9}', '{"score": 3}'])
    result = setup.complete(json_schema=SCHEMA)
    assert result.json == {"score": 3}
    repair = setup.provider.requests[1].messages
    assert repair[-2] == Message("assistant", '{"score": 9}')
    assert "did not match" in repair[-1].content and "score" in repair[-1].content
    assert result.usage.tokens_in == 200  # both calls counted


def test_invalid_json_twice_is_an_error() -> None:
    with pytest.raises(InvalidJsonError):
        Setup(["not json", '{"score": "four"}']).complete(json_schema=SCHEMA)


def test_invalid_json_can_be_returned_for_the_caller_to_handle() -> None:
    setup = Setup(["not json"])
    result = setup.complete(json_schema=SCHEMA, invalid_json="none")
    assert result.json is None and len(setup.provider.requests) == 1


# --- Usage and cost ---


def test_every_call_is_recorded_without_prompt_text() -> None:
    setup = Setup(["ok"])
    result = setup.complete(prompt_version="7")
    (call,) = setup.usage.calls
    assert (call.tenant_id, call.recording_id, call.task, call.model) == (
        "tenant-a",
        "rec-1",
        "analysis.scoring",
        "fake-mid",
    )
    assert (call.tokens_in, call.tokens_out, call.prompt_version, call.status) == (100, 20, "7", "ok")
    assert call.prompt_hash == result.prompt_hash and len(call.prompt_hash) == 64
    assert "fractions" not in json.dumps(call.model_dump(mode="json"))


def test_a_model_without_a_published_price_has_no_cost() -> None:
    assert Setup(["ok"]).complete().cost_usd is None


def test_cost_comes_from_the_published_prices() -> None:
    spec = CATALOG["openai:o3-mini"]
    # 1 000 000 input tokens of which 400 000 cached, and 100 000 output tokens, at $1.10 / $0.55 / $4.40 per million
    assert cost_usd(spec, 1_000_000, 400_000, 100_000) == pytest.approx(0.66 + 0.22 + 0.44)
    assert cost_usd(ModelSpec("x", "y"), 10, 0, 10) is None


def test_cache_writes_cost_their_own_published_price() -> None:
    luna = CATALOG["openai:gpt-6-luna"]
    # 1 000 000 input tokens: 200 000 read from the cache, 300 000 written to it, 500 000 plain; 100 000 output.
    # $0.10 plain, $0.01 cached, $0.125 cache write, $0.50 output per million (model page, 2026-10-24).
    assert cost_usd(luna, 1_000_000, 200_000, 100_000, 300_000) == pytest.approx(0.05 + 0.002 + 0.0375 + 0.05)
    # Without a separate write price, written tokens cost as input.
    assert cost_usd(CATALOG["openai:o3-mini"], 1_000_000, 0, 0, 300_000) == pytest.approx(1.10)


def test_the_prompt_hash_is_stable_and_depends_on_the_schema() -> None:
    setup = Setup(["ok", "ok", '{"score": 1}'])
    first, second, with_schema = setup.complete(), setup.complete(), setup.complete(json_schema=SCHEMA)
    assert first.prompt_hash == second.prompt_hash != with_schema.prompt_hash


def test_usage_adds_up() -> None:
    assert Usage(10, 5, 2).total == 15
