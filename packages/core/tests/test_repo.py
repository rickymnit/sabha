"""TenantRepo / SyncTenantRepo mechanics and the SystemRepo (plan task P1.6).

Cross-tenant isolation has its own suite in tests/security/test_tenant_isolation.py. This file checks that the
repositories work as repositories: model round trips, sorting, transactions with the outbox, and which
collections each kind of repository accepts.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from sabha_core.models import AuditEntry, IdentityLink, OutboxEvent, Person, Tenant
from sabha_core.quota import Plan
from sabha_core.repo import (
    COLLECTIONS,
    SYSTEM_COLLECTIONS,
    CollectionNotAllowedError,
    ImmutableCollectionError,
    MissingTenantError,
    OwnTenantRepo,
    SyncSystemRepo,
    SyncTenantRepo,
    SystemRepo,
    TenantRepo,
    TenantViolationError,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"repo_{uuid.uuid4().hex[:12]}"
    database = mongo_replica_set[name]
    # Transactions cannot create collections on MongoDB 7 in every case; create them up front as indexes.py will.
    for collection in ("people", "outbox"):
        database.create_collection(collection)
    yield database
    mongo_replica_set.drop_database(name)


# --- Collections ---


def test_collections_are_the_domain_model_plus_identities() -> None:
    # CLAUDE.md "Domain model", plus `identities` (ADR 0002), `idempotency_keys` (API conventions),
    # `llm_calls` (P5.1), `relay_state` (P2.5), `dlq` (P2.4) and `deliveries` (P2.7).
    assert set(COLLECTIONS) == {
        "tenants", "units", "users", "people", "recordings", "stage_runs", "transcripts", "rubrics", "analyses",
        "scores", "disputes", "usage_events", "outbox", "audit_log", "identities", "idempotency_keys", "llm_calls",
        "relay_state", "dlq", "deliveries",
    }  # fmt: skip
    assert set(SYSTEM_COLLECTIONS) == {"tenants", "outbox", "identities", "relay_state"}


@pytest.mark.parametrize("collection", ["tenants", "no_such_collection", "people "])
def test_tenant_repo_refuses_collections_it_cannot_scope(db: Database[dict[str, Any]], collection: str) -> None:
    with pytest.raises(CollectionNotAllowedError):
        SyncTenantRepo(db, collection, "t1", Person)


@pytest.mark.parametrize("collection", ["people", "recordings", "audit_log"])
def test_system_repo_refuses_tenant_collections(db: Database[dict[str, Any]], collection: str) -> None:
    with pytest.raises(CollectionNotAllowedError):
        SyncSystemRepo(db, collection, Person)


# --- Round trips ---


def test_insert_then_find_returns_an_equal_model(db: Database[dict[str, Any]]) -> None:
    repo = SyncTenantRepo(db, "people", "t1", Person)
    inserted = repo.insert_one(Person(name="Asha", unit_id="u1"))
    assert repo.find_one({"_id": inserted.id}) == inserted
    stored = db.people.find_one({"_id": inserted.id})
    assert stored is not None and "id" not in stored  # stored under _id only


def test_find_sorts_and_limits(db: Database[dict[str, Any]]) -> None:
    repo = SyncTenantRepo(db, "people", "t1", Person)
    repo.insert_many([Person(name=n) for n in ("Chitra", "Asha", "Bina")])
    assert [p.name for p in repo.find({}, sort=[("name", 1)], limit=2)] == ["Asha", "Bina"]


def test_duplicate_ids_are_reported_not_overwritten(db: Database[dict[str, Any]]) -> None:
    repo = SyncTenantRepo(db, "people", "t1", Person)
    repo.insert_one(Person(id="p1", name="Asha"))
    with pytest.raises(DuplicateKeyError):
        repo.insert_one(Person(id="p1", name="Someone else"))
    assert db.people.find_one({"_id": "p1"}, {"_id": 0, "name": 1}) == {"name": "Asha"}


def test_aggregate_returns_plain_rows(db: Database[dict[str, Any]]) -> None:
    repo = SyncTenantRepo(db, "people", "t1", Person)
    repo.insert_many([Person(name="Asha", unit_id="u1"), Person(name="Bina", unit_id="u1"), Person(name="C")])
    rows = repo.aggregate([{"$group": {"_id": "$unit_id", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}])
    assert rows == [{"_id": "u1", "n": 2}, {"_id": None, "n": 1}]


# --- Transactions: a change and its outbox event are written together or not at all (P2.5) ---


def test_sync_repos_share_a_transaction(
    mongo_replica_set: MongoClient[dict[str, Any]], db: Database[dict[str, Any]]
) -> None:
    people = SyncTenantRepo(db, "people", "t1", Person)
    outbox = SyncTenantRepo(db, "outbox", "t1", OutboxEvent)

    with mongo_replica_set.start_session() as session, pytest.raises(RuntimeError), session.start_transaction():
        people.insert_one(Person(id="p1", name="Asha"), session=session)
        outbox.insert_one(OutboxEvent(type="person.created", payload={"person_id": "p1"}), session=session)
        raise RuntimeError("abort")
    assert db.people.count_documents({}) == 0
    assert db.outbox.count_documents({}) == 0

    with mongo_replica_set.start_session() as session, session.start_transaction():
        people.insert_one(Person(id="p1", name="Asha"), session=session)
        outbox.insert_one(OutboxEvent(type="person.created", payload={"person_id": "p1"}), session=session)
    assert db.people.count_documents({"tenant_id": "t1"}) == 1
    assert db.outbox.count_documents({"tenant_id": "t1"}) == 1


def test_async_repos_share_a_transaction(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    async def scenario() -> None:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        try:
            people = TenantRepo(client[db.name], "people", "t1", Person)
            outbox = TenantRepo(client[db.name], "outbox", "t1", OutboxEvent)
            async with client.start_session() as session, await session.start_transaction():
                await people.insert_one(Person(id="p1", name="Asha"), session=session)
                await outbox.insert_one(OutboxEvent(type="person.created", payload={}), session=session)
            assert await people.count({}) == 1
            assert await outbox.count({}) == 1
        finally:
            await client.close()

    asyncio.run(scenario())


# --- SystemRepo: the unscoped exception for tenants, outbox and identities ---


def test_system_repo_reads_across_tenants(db: Database[dict[str, Any]]) -> None:
    for tenant in ("t1", "t2"):
        SyncTenantRepo(db, "outbox", tenant, OutboxEvent).insert_one(OutboxEvent(type="x", payload={}))
    relay = SyncSystemRepo(db, "outbox", OutboxEvent)
    assert sorted(e.tenant_id for e in relay.find({})) == ["t1", "t2"]


def test_system_repo_manages_tenants(db: Database[dict[str, Any]]) -> None:
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    created = tenants.insert_one(Tenant.from_profile("school", name="Green Valley School", plan=Plan.PILOT))
    assert tenants.find_one({"_id": created.id}) == created


def test_async_system_repo_exists_for_login(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    async def scenario() -> int:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        try:
            return await SystemRepo(client[db.name], "identities", IdentityLink).count({})
        finally:
            await client.close()

    assert asyncio.run(scenario()) == 0


# --- OwnTenantRepo: a tenant's own settings, through its own id only (P1.7) ---


def _own(mongo_uri: str, db: Database[dict[str, Any]], tenant_id: str, scenario: Any) -> Any:
    async def run() -> Any:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        try:
            return await scenario(OwnTenantRepo(client[db.name], tenant_id))
        finally:
            await client.close()

    return asyncio.run(run())


def _two_tenants(db: Database[dict[str, Any]]) -> None:
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    tenants.insert_one(Tenant.from_profile("school", name="Sunrise", plan=Plan.PILOT, id="t1"))
    tenants.insert_one(Tenant.from_profile("company", name="Brightpath", plan=Plan.PILOT, id="t2"))


def test_own_tenant_repo_reads_only_its_own_tenant(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    _two_tenants(db)

    async def scenario(repo: OwnTenantRepo) -> Tenant | None:
        return await repo.get()

    found = _own(mongo_uri, db, "t1", scenario)
    assert found is not None and found.name == "Sunrise"


def test_own_tenant_repo_changes_only_its_own_tenant(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    _two_tenants(db)

    async def scenario(repo: OwnTenantRepo) -> int:
        return await repo.update_settings({"name": "Sunrise Public School", "enabled_types": ["teaching"]})

    assert _own(mongo_uri, db, "t1", scenario) == 1
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    mine, other = tenants.find_one({"_id": "t1"}), tenants.find_one({"_id": "t2"})
    assert mine is not None and mine.name == "Sunrise Public School" and mine.enabled_types == ["teaching"]
    assert other is not None and other.name == "Brightpath" and other.enabled_types == ["reception", "meeting", "sales"]


@pytest.mark.parametrize(
    "fields",
    [
        {"plan": "growth"},  # plans change through Sabha, never from the tenant's own settings
        {"profile": "company"},
        {"region": "us-east-1"},
        {"_id": "t2"},
        {"tenant_id": "t2"},
        {"retention_days": 1},
        {"name": "ok", "plan": "growth"},  # one bad field refuses the whole update
        {},
    ],
)
def test_own_tenant_repo_refuses_other_fields(mongo_uri: str, db: Database[dict[str, Any]], fields: Any) -> None:
    _two_tenants(db)

    async def scenario(repo: OwnTenantRepo) -> int:
        return await repo.update_settings(fields)

    with pytest.raises(TenantViolationError):
        _own(mongo_uri, db, "t1", scenario)
    unchanged = SyncSystemRepo(db, "tenants", Tenant).find_one({"_id": "t1"})
    assert unchanged is not None and unchanged.name == "Sunrise" and unchanged.plan == Plan.PILOT


@pytest.mark.parametrize("tenant_id", ["", "   ", None])
def test_own_tenant_repo_needs_a_tenant_id(mongo_uri: str, db: Database[dict[str, Any]], tenant_id: Any) -> None:
    with pytest.raises(MissingTenantError):
        OwnTenantRepo(db, tenant_id)  # type: ignore[arg-type]  # a sync handle is enough: it fails before any use


# --- The audit log is append-only (P1.8) ---


def _entry() -> AuditEntry:
    return AuditEntry(actor_user_id="u1", actor_role="owner", action="recording.play", target_type="recording",
                      target_id="r1")  # fmt: skip


SYNC_CHANGES = [
    ("update_one", lambda r: r.update_one({}, {"$set": {"action": "x"}})),
    ("update_one upsert", lambda r: r.update_one({"_id": "new"}, {"$set": {"action": "x"}}, upsert=True)),
    ("update_many", lambda r: r.update_many({}, {"$set": {"action": "x"}})),
    ("delete_one", lambda r: r.delete_one({})),
    ("delete_many", lambda r: r.delete_many({})),
]


@pytest.mark.parametrize(("name", "change"), SYNC_CHANGES, ids=[n for n, _ in SYNC_CHANGES])
def test_audit_entries_cannot_be_changed_or_deleted(db: Database[dict[str, Any]], name: str, change: Any) -> None:
    repo = SyncTenantRepo(db, "audit_log", "t1", AuditEntry)
    entry = repo.insert_one(_entry())
    with pytest.raises(ImmutableCollectionError):
        change(repo)
    assert repo.find({}) == [entry]


ASYNC_CHANGES = [
    ("update_one", lambda r: r.update_one({}, {"$set": {"action": "x"}})),
    ("update_many", lambda r: r.update_many({}, {"$set": {"action": "x"}})),
    ("delete_one", lambda r: r.delete_one({})),
    ("delete_many", lambda r: r.delete_many({})),
]


@pytest.mark.parametrize(("name", "change"), ASYNC_CHANGES, ids=[n for n, _ in ASYNC_CHANGES])
def test_async_audit_entries_cannot_be_changed_or_deleted(
    mongo_uri: str, db: Database[dict[str, Any]], name: str, change: Any
) -> None:
    async def scenario() -> list[AuditEntry]:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        try:
            repo = TenantRepo(client[db.name], "audit_log", "t1", AuditEntry)
            await repo.insert_one(_entry())
            with pytest.raises(ImmutableCollectionError):
                await change(repo)
            return await repo.find({})
        finally:
            await client.close()

    assert len(asyncio.run(scenario())) == 1


def test_audit_entries_can_still_be_added_and_read(db: Database[dict[str, Any]]) -> None:
    repo = SyncTenantRepo(db, "audit_log", "t1", AuditEntry)
    repo.insert_many([_entry(), _entry()])
    assert repo.count({"action": "recording.play"}) == 2
