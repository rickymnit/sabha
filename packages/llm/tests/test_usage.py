"""MongoUsage writes each call through the tenant-scoped repository (plan task P5.1)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pymongo import MongoClient

from sabha_core.models import LlmCall
from sabha_llm.usage import MongoUsage

pytestmark = pytest.mark.integration


def test_calls_are_stored_under_their_tenant(mongo_replica_set: MongoClient[dict[str, Any]]) -> None:
    db = mongo_replica_set[f"llm_{uuid.uuid4().hex[:12]}"]
    try:
        sink = MongoUsage(db)
        for tenant in ("tenant-a", "tenant-b"):
            sink.record(
                LlmCall(tenant_id=tenant, task="analysis.scoring", provider="openai", model="o3-mini",
                        prompt_hash="0" * 64, status="ok", tokens_in=10, tokens_out=2, latency_ms=5, attempt=1)
            )  # fmt: skip
        assert sorted(d["tenant_id"] for d in db.llm_calls.find()) == ["tenant-a", "tenant-b"]
    finally:
        mongo_replica_set.drop_database(db.name)
