"""eval/role_corrections.py: reviewer corrections of speaker roles against Sabha's own decision."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database
from role_corrections import corrections

from sabha_core.models import Recording, Tenant
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.state import RecordingStatus

pytestmark = pytest.mark.integration


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"corrections_{uuid.uuid4().hex[:12]}"
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def test_a_correction_is_listed_against_the_automatic_decision(db: Database[dict[str, Any]]) -> None:
    SyncSystemRepo(db, "tenants", Tenant).insert_one(Tenant.from_profile("company", name="Acme", plan=Plan.PILOT,
                                                                          id="acme"))  # fmt: skip
    recordings = SyncTenantRepo(db, "recordings", "acme", Recording)
    corrected = recordings.insert_one(Recording(type=ConversationType.SUPPORT, status=RecordingStatus.COMPLETED,
                                                consent_ref="c", confirmed_roles={"S0": "customer",
                                                                                  "S1": "support_agent"}))  # fmt: skip
    recordings.insert_one(Recording(type=ConversationType.SUPPORT, status=RecordingStatus.COMPLETED, consent_ref="c"))
    auto = {"S0": {"role": "support_agent", "confidence": 0.93, "method": "llm_tiebreak"},
            "S1": {"role": "customer", "confidence": 0.93, "method": "llm_tiebreak"}}  # fmt: skip
    stored = {f"acme/{corrected.id}/transcribe@v1/roles_auto@v1.json": json.dumps(auto).encode()}

    def read(key: str) -> bytes:
        if key not in stored:
            raise FileNotFoundError(key)
        return stored[key]

    (row,) = corrections(db, read, conversation_type="support")  # the uncorrected recording is not listed
    assert (row["recording_id"], row["agree"], row["evidence"]) == (corrected.id, False, None)
    assert row["automatic"] == {"staff": "S0", "methods": ["llm_tiebreak"]} and row["reviewer"] == {"staff": "S1"}
