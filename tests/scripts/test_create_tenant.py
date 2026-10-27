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


def test_the_allowance_is_set_only_when_given(db: Database[dict[str, Any]]) -> None:
    script = load_script()
    common = {"profile": "school", "plan": Plan.STARTER, "owner_name": "A", "issuer": "https://idp.example/"}
    with_hours, _ = script.create_tenant(db, name="One", owner_email="a@one.example", audio_hours=100, **common)
    without, _ = script.create_tenant(db, name="Two", owner_email="a@two.example", **common)
    assert db.tenants.find_one({"_id": with_hours.id})["audio_hours_allowance"] == 100  # type: ignore[index]
    assert db.tenants.find_one({"_id": without.id})["audio_hours_allowance"] is None  # type: ignore[index]


# --- scripts/admin/set_plan.py ---


def load_set_plan() -> ModuleType:
    spec = importlib.util.spec_from_file_location("set_plan", SCRIPT.with_name("set_plan.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_set_plan_changes_plan_and_allowance_of_one_tenant(db: Database[dict[str, Any]]) -> None:
    create, set_plan = load_script(), load_set_plan()
    common = {"profile": "school", "plan": Plan.PILOT, "owner_name": "A", "issuer": "https://idp.example/"}
    mine, _ = create.create_tenant(db, name="One", owner_email="a@one.example", **common)
    other, _ = create.create_tenant(db, name="Two", owner_email="a@two.example", **common)

    changed = set_plan.set_plan(db, mine.id, plan=Plan.STARTER, audio_hours=100)
    assert (changed.plan, changed.audio_hours_allowance) == (Plan.STARTER, 100)
    stored = db.tenants.find_one({"_id": mine.id})
    assert stored is not None and (stored["plan"], stored["audio_hours_allowance"]) == ("starter", 100)
    untouched = db.tenants.find_one({"_id": other.id})
    assert untouched is not None and (untouched["plan"], untouched["audio_hours_allowance"]) == ("pilot", None)

    set_plan.set_plan(db, mine.id, plan=Plan.GROWTH)  # the allowance is kept when not given
    assert db.tenants.find_one({"_id": mine.id})["audio_hours_allowance"] == 100  # type: ignore[index]
    set_plan.set_plan(db, mine.id, audio_hours=None)  # removed
    assert db.tenants.find_one({"_id": mine.id})["audio_hours_allowance"] is None  # type: ignore[index]


def test_set_plan_refuses_bad_input(db: Database[dict[str, Any]]) -> None:
    create, set_plan = load_script(), load_set_plan()
    tenant, _ = create.create_tenant(db, name="One", profile="school", plan=Plan.PILOT, owner_email="a@one.example",
                                     owner_name="A", issuer="https://idp.example/")  # fmt: skip
    with pytest.raises(ValueError, match="audio_hours_allowance"):
        set_plan.set_plan(db, tenant.id, audio_hours=0)
    with pytest.raises(LookupError):
        set_plan.set_plan(db, "no-such-tenant", plan=Plan.GROWTH)
    assert db.tenants.find_one({"_id": tenant.id})["audio_hours_allowance"] is None  # type: ignore[index]
