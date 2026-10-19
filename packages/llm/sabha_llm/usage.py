"""Where the gateway records each provider call: the tenant-scoped `llm_calls` collection (plan task P5.1)."""

from __future__ import annotations

from typing import Any, Protocol

from pymongo.database import Database

from sabha_core.models import LlmCall
from sabha_core.repo import SyncTenantRepo


class UsageSink(Protocol):
    def record(self, call: LlmCall) -> None: ...


class MongoUsage:
    """Writes each LlmCall through the tenant-scoped repository of the call's tenant."""

    def __init__(self, database: Database[dict[str, Any]]) -> None:
        self._store = database

    def record(self, call: LlmCall) -> None:
        calls = SyncTenantRepo(self._store, "llm_calls", call.tenant_id, LlmCall)
        calls.insert_one(call)


class MemoryUsage:
    """For tests."""

    def __init__(self) -> None:
        self.calls: list[LlmCall] = []

    def record(self, call: LlmCall) -> None:
        self.calls.append(call)
