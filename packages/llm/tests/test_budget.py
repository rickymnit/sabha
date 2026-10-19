"""Daily token budgets in Redis (plan task P5.1), and the gateway refusing calls once a budget is used up."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from redis import Redis

from sabha_llm.budget import TokenBudget
from sabha_llm.errors import BudgetExceededError, BudgetUnavailableError
from sabha_llm.gateway import Gateway
from sabha_llm.providers.fake import FakeProvider
from sabha_llm.types import Message
from sabha_llm.usage import MemoryUsage

pytestmark = pytest.mark.integration

DAY = datetime(2026, 10, 19, 10, tzinfo=UTC)


@pytest.fixture
def redis(redis_url: str) -> Iterator[Redis]:
    client = Redis.from_url(redis_url)
    client.flushdb()
    yield client
    client.close()


def test_a_tenant_over_its_daily_budget_is_refused(redis: Redis) -> None:
    budget = TokenBudget(redis, tenant_daily=100, global_daily=None, now=lambda: DAY)
    budget.check("tenant-a")
    budget.charge("tenant-a", 100)
    with pytest.raises(BudgetExceededError, match="tenant-a"):
        budget.check("tenant-a")
    budget.check("tenant-b")  # other tenants are unaffected


def test_the_global_budget_covers_every_tenant(redis: Redis) -> None:
    budget = TokenBudget(redis, tenant_daily=None, global_daily=150, now=lambda: DAY)
    budget.charge("tenant-a", 100)
    budget.charge("tenant-b", 60)
    with pytest.raises(BudgetExceededError, match="global"):
        budget.check("tenant-c")


def test_budgets_reset_each_day(redis: Redis) -> None:
    today = TokenBudget(redis, tenant_daily=10, global_daily=None, now=lambda: DAY)
    today.charge("tenant-a", 10)
    tomorrow = TokenBudget(redis, tenant_daily=10, global_daily=None, now=lambda: DAY.replace(day=20))
    tomorrow.check("tenant-a")


def test_counters_expire(redis: Redis) -> None:
    TokenBudget(redis, tenant_daily=10, global_daily=None, now=lambda: DAY).charge("tenant-a", 1)
    assert 0 < redis.ttl("llmb:t:tenant-a:20261019") <= 2 * 24 * 3600


def test_without_limits_nothing_is_checked() -> None:
    TokenBudget(None, tenant_daily=None, global_daily=None).check("tenant-a")


def test_limits_without_redis_are_a_configuration_error() -> None:
    with pytest.raises(ValueError):
        TokenBudget(None, tenant_daily=10, global_daily=None)


def test_unreadable_counters_stop_calls() -> None:
    broken = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    with pytest.raises(BudgetUnavailableError):
        TokenBudget(broken, tenant_daily=10, global_daily=None).check("tenant-a")


def test_the_gateway_charges_tokens_and_blocks_past_the_budget(redis: Redis) -> None:
    provider = FakeProvider(["ok", "ok", "never sent"])  # 120 tokens a call
    gateway = Gateway(
        providers={"fake": provider},
        models={"small": "fake:fake-small", "mid": "fake:fake-mid"},
        budget=TokenBudget(redis, tenant_daily=200, global_daily=None, now=lambda: DAY),
        usage=MemoryUsage(),
    )

    def call() -> None:
        gateway.complete(task="analysis.scoring", messages=[Message("user", "hi")], tenant_id="tenant-a")

    call()
    call()  # 120 < 200 before this call: allowed, ends at 240
    with pytest.raises(BudgetExceededError):
        call()
    assert len(provider.requests) == 2
