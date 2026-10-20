"""Token-bucket rate limits in Redis: soft limit, hard ceiling, refill, both buckets, headers, and Redis down."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from sabha_api.ratelimit import Bucket, Decision, RateLimitedError, RateLimiter


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"  # async tests run on anyio's pytest plugin (installed with Starlette)


@pytest.fixture
async def limiter(redis_url: str) -> AsyncIterator[RateLimiter]:
    redis = Redis.from_url(redis_url)
    await redis.flushdb()
    yield RateLimiter(redis)
    await redis.aclose()


async def hits(limiter: RateLimiter, buckets: list[Bucket], n: int) -> list[Decision]:
    out = []
    for _ in range(n):
        decision = await limiter.hit(buckets)
        assert decision is not None
        out.append(decision)
    return out


def test_bucket_arithmetic() -> None:
    bucket = Bucket("tenant", "t1", per_minute=60, burst_factor=1.5)
    assert bucket.key == "rl:tenant:t1"
    assert bucket.refill_per_ms == pytest.approx(0.001)
    assert bucket.floor == -30
    with pytest.raises(ValueError):
        Bucket("user", "u", per_minute=0, tenant_id="t1")
    with pytest.raises(ValueError):
        Bucket("user", "u", per_minute=10, burst_factor=0.5, tenant_id="t1")


def test_user_buckets_are_keyed_by_tenant() -> None:
    # /tenant-check finding 1: equal user ids in two tenants must never share a budget.
    a = Bucket("user", "u1", per_minute=10, tenant_id="tenant-a")
    b = Bucket("user", "u1", per_minute=10, tenant_id="tenant-b")
    assert a.key == "rl:user:tenant-a:u1" and b.key == "rl:user:tenant-b:u1"
    with pytest.raises(ValueError, match="tenant_id"):
        Bucket("user", "u1", per_minute=10)
    with pytest.raises(ValueError, match="tenant_id"):
        Bucket("tenant", "tenant-a", per_minute=10, tenant_id="tenant-b")
    with pytest.raises(ValueError, match="scope"):
        Bucket("global", "x", per_minute=10)


def test_headers() -> None:
    assert Decision(True, 60, 5, 55).headers() == {
        "RateLimit-Limit": "60",
        "RateLimit-Remaining": "5",
        "RateLimit-Reset": "55",
    }
    assert Decision(False, 60, 0, 90, retry_after_s=2).headers()["Retry-After"] == "2"


@pytest.mark.integration
@pytest.mark.anyio
async def test_soft_limit_then_hard_ceiling(limiter: RateLimiter) -> None:
    bucket = [Bucket("tenant", "t1", per_minute=10, burst_factor=1.5)]
    decisions = await hits(limiter, bucket, 16)
    assert [d.remaining for d in decisions[:10]] == [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    # Past the soft limit requests still succeed, reporting nothing left, up to 10 * 0.5 = 5 more.
    assert all(d.allowed and d.remaining == 0 for d in decisions[10:15])
    refused = decisions[15]
    assert not refused.allowed
    assert refused.retry_after_s is not None and 1 <= refused.retry_after_s <= 6


@pytest.mark.integration
@pytest.mark.anyio
async def test_a_refused_request_takes_no_tokens(limiter: RateLimiter) -> None:
    bucket = [Bucket("tenant", "t2", per_minute=2, burst_factor=1.0)]
    first, second, third, fourth = await hits(limiter, bucket, 4)
    assert (first.allowed, second.allowed, third.allowed, fourth.allowed) == (True, True, False, False)
    assert third.retry_after_s == fourth.retry_after_s  # waiting is not made longer by retrying


@pytest.mark.integration
@pytest.mark.anyio
async def test_tokens_refill_over_time(limiter: RateLimiter) -> None:
    bucket = [Bucket("user", "u1", per_minute=60, burst_factor=1.0, tenant_id="t1")]  # one token a second
    await hits(limiter, bucket, 60)
    [refused] = await hits(limiter, bucket, 1)
    assert not refused.allowed
    assert refused.retry_after_s == 1
    await asyncio.sleep(1.1)
    [again] = await hits(limiter, bucket, 1)
    assert again.allowed


@pytest.mark.integration
@pytest.mark.anyio
async def test_the_tighter_bucket_decides_and_neither_is_charged_on_refusal(limiter: RateLimiter) -> None:
    tenant = Bucket("tenant", "t3", per_minute=100, burst_factor=1.0)
    user = Bucket("user", "u3", per_minute=3, burst_factor=1.0, tenant_id="t3")
    decisions = await hits(limiter, [tenant, user], 4)
    assert [d.allowed for d in decisions] == [True, True, True, False]
    assert decisions[0].limit == 3  # headers describe the user's bucket, the tighter one
    # The tenant bucket paid for the three allowed requests only: another user of the tenant still has 97.
    [other] = await hits(limiter, [tenant, Bucket("user", "u4", per_minute=1000, burst_factor=1.0, tenant_id="t3")], 1)
    assert other.limit == 100
    assert other.remaining == 96


@pytest.mark.integration
@pytest.mark.anyio
async def test_the_same_user_id_in_another_tenant_has_its_own_budget(limiter: RateLimiter) -> None:
    await hits(limiter, [Bucket("user", "same", per_minute=2, burst_factor=1.0, tenant_id="ta")], 3)
    [other] = await hits(limiter, [Bucket("user", "same", per_minute=2, burst_factor=1.0, tenant_id="tb")], 1)
    assert other.allowed and other.remaining == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_one_tenant_cannot_use_another_tenants_budget(limiter: RateLimiter) -> None:
    await hits(limiter, [Bucket("tenant", "busy", per_minute=5, burst_factor=1.0)], 6)
    [quiet] = await hits(limiter, [Bucket("tenant", "quiet", per_minute=5, burst_factor=1.0)], 1)
    assert quiet.allowed and quiet.remaining == 4


@pytest.mark.integration
@pytest.mark.anyio
async def test_concurrent_hits_never_overspend(limiter: RateLimiter) -> None:
    bucket = [Bucket("tenant", "race", per_minute=50, burst_factor=1.0)]
    results = await asyncio.gather(*(limiter.hit(bucket) for _ in range(80)))
    assert sum(1 for d in results if d is not None and d.allowed) == 50


@pytest.mark.anyio
async def test_redis_down_allows_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    limiter = RateLimiter(redis)
    assert await limiter.hit([Bucket("tenant", "t", per_minute=1)]) is None
    assert await limiter.enforce([Bucket("tenant", "t", per_minute=1)]) == {}
    assert any(r.message == "rate limiter unavailable; allowing the request" for r in caplog.records)
    await redis.aclose()


def test_refusal_is_a_429_problem_with_retry_after(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)

    @app.get("/v1/limited")
    async def limited() -> None:
        raise RateLimitedError(Decision(False, 60, 0, 70, retry_after_s=3))

    response = client.get("/v1/limited")
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert response.headers["retry-after"] == "3"
    assert response.headers["ratelimit-limit"] == "60"
