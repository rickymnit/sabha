"""scripts/admin/enable_type.py: a new type switched on for existing tenants of a profile, audited, within limits."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import Tenant
from sabha_core.profiles import ConversationType, ProfileName
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "admin" / "enable_type.py"
T = ConversationType
BEFORE = [T.RECEPTION, T.MEETING, T.SALES]  # a company created before support existed


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("enable_type", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up while being defined
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"admin_{uuid.uuid4().hex[:12]}"
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def add(db: Database[dict[str, Any]], tenant_id: str, profile: str, plan: Plan, types: list[ConversationType]) -> None:
    tenant = Tenant.from_profile(profile, name=tenant_id, plan=plan, id=tenant_id, enabled_types=types)
    SyncSystemRepo(db, "tenants", Tenant).insert_one(tenant)


def test_switches_support_on_for_existing_companies_only_and_audits_it(
    mongo_replica_set: MongoClient[dict[str, Any]], db: Database[dict[str, Any]]
) -> None:
    add(db, "acme", "company", Plan.PILOT, BEFORE)
    add(db, "small", "company", Plan.STARTER, [T.SALES, T.MEETING])  # Starter allows 2 types: no room
    add(db, "school", "school", Plan.PILOT, [T.TEACHING, T.RECEPTION])
    script = load_script()

    dry = script.enable_type(mongo_replica_set, db, T.SUPPORT, ProfileName.COMPANY, dry_run=True)
    assert (dry.enabled, dry.over_plan_limit) == (["acme"], ["small"])
    assert db.tenants.count_documents({"enabled_types": "support"}) == 0

    done = script.enable_type(mongo_replica_set, db, T.SUPPORT, ProfileName.COMPANY)
    assert (done.enabled, done.over_plan_limit) == (["acme"], ["small"])
    stored = {t["_id"]: t["enabled_types"] for t in db.tenants.find()}
    assert stored == {"acme": ["reception", "meeting", "sales", "support"], "small": ["sales", "meeting"],
                      "school": ["teaching", "reception"]}  # fmt: skip
    (entry,) = db.audit_log.find()
    assert (entry["tenant_id"], entry["action"], entry["actor_user_id"]) == ("acme", "settings.update", "system")
    assert entry["meta"]["after"]["enabled_types"][-1] == "support"

    again = script.enable_type(mongo_replica_set, db, T.SUPPORT, ProfileName.COMPANY)
    assert (again.enabled, again.already_on) == ([], ["acme"]) and db.audit_log.count_documents({}) == 1
