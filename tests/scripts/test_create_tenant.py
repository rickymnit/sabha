"""scripts/admin/create_tenant.py: a tenant from a profile plus its first owner's invite, in one transaction."""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.quota import Plan

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "admin" / "create_tenant.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("create_tenant", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"admin_{uuid.uuid4().hex[:12]}"
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def test_creates_the_tenant_owner_and_pending_invite(db: Database[dict[str, Any]]) -> None:
    script = load_script()
    tenant, owner = script.create_tenant(
        db,
        name="Green Valley School",
        profile="school",
        plan=Plan.PILOT,
        owner_email="Principal@Example.com",
        owner_name="Asha Rao",
        issuer="https://sabha-dev.eu.auth0.com/",
    )
    stored = db.tenants.find_one({"_id": tenant.id})
    assert stored is not None and stored["profile"] == "school" and stored["labels"]["person"]
    user = db.users.find_one({"_id": owner.id})
    assert user is not None
    assert (user["tenant_id"], user["role"], user["status"], user["email"]) == (
        tenant.id,
        "owner",
        "invited",
        "principal@example.com",
    )
    invite = db.identities.find_one({"user_id": owner.id})
    assert invite is not None
    assert (invite["tenant_id"], invite["issuer"], invite["subject"]) == (
        tenant.id,
        "https://sabha-dev.eu.auth0.com",
        None,
    )
