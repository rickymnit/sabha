"""Daily token budgets per tenant and overall, counted in Redis (plan task P5.1).

Before a call, `check` refuses (BudgetExceededError) when today's tokens already reached a limit; after it,
`charge` adds the tokens the provider reported. Days are UTC; counters expire after two days. A call that starts
under the limit may end above it, by at most one call's tokens. Unset limits mean no check at all.

If Redis cannot be read while a limit is set, calls stop (BudgetUnavailableError): spending without a working
limit is the worse failure. A failed `charge` is logged, since the tokens were already spent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from redis import Redis
from redis.exceptions import RedisError

from sabha_llm.errors import BudgetExceededError, BudgetUnavailableError

log = logging.getLogger("sabha.llm.budget")

_TTL_S = 2 * 24 * 3600


class TokenBudget:
    def __init__(
        self,
        redis: Redis | None,
        *,
        tenant_daily: int | None,
        global_daily: int | None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if redis is None and (tenant_daily or global_daily):
            raise ValueError("token budgets need Redis")
        self._redis = redis
        self._tenant_daily = tenant_daily
        self._global_daily = global_daily
        self._now = now

    def _keys(self, tenant_id: str) -> tuple[str, str]:
        day = self._now().strftime("%Y%m%d")
        return f"llmb:t:{tenant_id}:{day}", f"llmb:g:{day}"

    def check(self, tenant_id: str) -> None:
        if self._redis is None or not (self._tenant_daily or self._global_daily):
            return
        tenant_key, global_key = self._keys(tenant_id)
        try:
            tenant_used, global_used = (int(v or 0) for v in self._redis.mget([tenant_key, global_key]))
        except RedisError as exc:
            raise BudgetUnavailableError("token budgets cannot be read; LLM calls are paused") from exc
        if self._tenant_daily and tenant_used >= self._tenant_daily:
            raise BudgetExceededError(f"tenant {tenant_id} used its daily LLM token budget")
        if self._global_daily and global_used >= self._global_daily:
            raise BudgetExceededError("the global daily LLM token budget is used up")

    def charge(self, tenant_id: str, tokens: int) -> None:
        if self._redis is None or tokens <= 0:
            return
        tenant_key, global_key = self._keys(tenant_id)
        try:
            pipe = self._redis.pipeline()
            for key in (tenant_key, global_key):
                pipe.incrby(key, tokens)
                pipe.expire(key, _TTL_S)
            pipe.execute()
        except RedisError as exc:
            log.warning("could not count LLM tokens", extra={"error_type": type(exc).__name__, "tokens": tokens})
