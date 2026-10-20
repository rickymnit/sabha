"""Per-tenant and per-user API rate limits: token buckets in Redis (plan task P7.2).

Each bucket holds up to `per_minute` tokens and refills at `per_minute / 60` per second; a request takes one token
from every bucket that applies (its tenant's and its user's). A bucket may go below zero down to a hard ceiling of
`per_minute * (burst_factor - 1)` extra requests: between the soft limit and the ceiling requests still succeed, and
`RateLimit-Remaining: 0` tells well-behaved clients to slow down. Past the ceiling the API answers 429 problem+json
(code `rate_limited`) with `Retry-After`. A refused request takes no tokens.

All buckets for a request are checked and updated in one Lua script, so concurrent API processes cannot overspend,
and the clock is Redis's own (`TIME`), so API hosts with skewed clocks agree.

Response headers (IETF draft "RateLimit header fields for HTTP", the widely deployed three-field form):
`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (seconds until the bucket is full again), from the most
constrained bucket.

If Redis is unreachable the request is allowed and a warning is logged with the reason: rate limiting protects
capacity, and refusing every request while Redis restarts would be the bigger outage. This is deliberate and
logged, never silent.

Wiring: the auth dependency (P1.5) knows the tenant and user and calls `RateLimiter.hit`.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from sabha_api.errors import ApiError

log = logging.getLogger("sabha.api.ratelimit")

KEY_PREFIX = "rl"

# KEYS: one per bucket. ARGV[1]: cost; then for each bucket: capacity, refill per ms, floor (<= 0).
# Returns {allowed (0/1), retry_after_ms, tokens_1, ..., tokens_n}; tokens are strings because Redis truncates Lua
# numbers to integers on the way out.
_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local cost = tonumber(ARGV[1])
local tokens, allowed, retry = {}, 1, 0
for i = 1, #KEYS do
  local base = 2 + (i - 1) * 3
  local cap, rate, floor = tonumber(ARGV[base]), tonumber(ARGV[base + 1]), tonumber(ARGV[base + 2])
  local saved = redis.call('HMGET', KEYS[i], 'tokens', 'ts')
  local tk = tonumber(saved[1]) or cap
  local ts = tonumber(saved[2]) or now
  tk = math.min(cap, tk + math.max(0, now - ts) * rate)
  tokens[i] = tk
  if tk - cost < floor then
    allowed = 0
    retry = math.max(retry, math.ceil((floor + cost - tk) / rate))
  end
end
local out = {allowed, retry}
for i = 1, #KEYS do
  local base = 2 + (i - 1) * 3
  local cap, rate = tonumber(ARGV[base]), tonumber(ARGV[base + 1])
  local tk = tokens[i]
  if allowed == 1 then tk = tk - cost end
  redis.call('HSET', KEYS[i], 'tokens', tostring(tk), 'ts', now)
  redis.call('PEXPIRE', KEYS[i], math.ceil((cap - tk) / rate) + 1000)
  out[#out + 1] = tostring(tk)
end
return out
"""


@dataclass(frozen=True, slots=True)
class Bucket:
    scope: str  # "tenant" or "user"
    id: str
    per_minute: int
    burst_factor: float = 1.5
    # Required for "user": a user's bucket lives under their tenant, so equal user ids in two tenants never share a
    # budget (golden rule 1).
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        if self.per_minute < 1 or self.burst_factor < 1:
            raise ValueError("per_minute must be >= 1 and burst_factor >= 1")
        if self.scope not in ("tenant", "user"):
            raise ValueError(f"unknown bucket scope {self.scope!r}")
        if self.scope == "user" and not self.tenant_id:
            raise ValueError("a user bucket needs the user's tenant_id")
        if self.scope == "tenant" and self.tenant_id not in (None, self.id):
            raise ValueError("a tenant bucket's id is its tenant_id")

    @property
    def key(self) -> str:
        if self.scope == "user":
            return f"{KEY_PREFIX}:user:{self.tenant_id}:{self.id}"
        return f"{KEY_PREFIX}:tenant:{self.id}"

    @property
    def refill_per_ms(self) -> float:
        return self.per_minute / 60_000

    @property
    def floor(self) -> float:
        return -self.per_minute * (self.burst_factor - 1)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    reset_s: int
    retry_after_s: int | None = None

    def headers(self) -> dict[str, str]:
        headers = {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(self.remaining),
            "RateLimit-Reset": str(self.reset_s),
        }
        if self.retry_after_s is not None:
            headers["Retry-After"] = str(self.retry_after_s)
        return headers


class RateLimitedError(ApiError):
    status, code, title = 429, "rate_limited", "Too many requests"

    def __init__(self, decision: Decision) -> None:
        super().__init__(
            f"Too many requests. Try again in {decision.retry_after_s} seconds.", headers=decision.headers()
        )


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script: Any = redis.register_script(_SCRIPT)

    async def hit(self, buckets: Sequence[Bucket], cost: int = 1) -> Decision | None:
        """Take `cost` tokens from every bucket, or none if any is past its ceiling.

        None means the limiter could not decide (Redis unavailable) and the request goes ahead; the reason is logged.
        """
        if not buckets:
            raise ValueError("at least one bucket")
        args: list[float] = [cost]
        for bucket in buckets:
            args += [bucket.per_minute, bucket.refill_per_ms, bucket.floor]
        try:
            raw = await self._script(keys=[b.key for b in buckets], args=args)
        except RedisError as exc:
            log.warning("rate limiter unavailable; allowing the request", extra={"error_type": type(exc).__name__})
            return None
        allowed, retry_ms, *tokens = raw
        # Report the bucket with the fewest tokens left relative to its size.
        bucket, left = min(zip(buckets, (float(t) for t in tokens), strict=True), key=lambda p: p[1] / p[0].per_minute)
        return Decision(
            allowed=bool(int(allowed)),
            limit=bucket.per_minute,
            remaining=max(0, math.floor(left)),
            reset_s=math.ceil((bucket.per_minute - left) / bucket.refill_per_ms / 1000),
            retry_after_s=max(1, math.ceil(int(retry_ms) / 1000)) if not int(allowed) else None,
        )

    async def enforce(self, buckets: Sequence[Bucket], cost: int = 1) -> dict[str, str]:
        """`hit`, raising RateLimitedError past the ceiling; returns the headers to put on the response."""
        decision = await self.hit(buckets, cost)
        if decision is None:
            return {}
        if not decision.allowed:
            raise RateLimitedError(decision)
        return decision.headers()
