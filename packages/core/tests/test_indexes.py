"""indexes.py: every collection's indexes, created idempotently at start-up (plan task P1.6)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.database import Database

from sabha_core.indexes import INDEXES, ensure_indexes, ensure_indexes_async
from sabha_core.repo import COLLECTIONS, SYSTEM_COLLECTIONS

pytestmark = pytest.mark.integration


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"idx_{uuid.uuid4().hex[:12]}"
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def keys(db: Database[dict[str, Any]], collection: str) -> dict[str, tuple[list[tuple[str, int]], bool]]:
    """name → (key fields, unique) for every index except _id."""
    return {
        name: (list(info["key"]), bool(info.get("unique", False)))
        for name, info in db[collection].index_information().items()
        if name != "_id_"
    }


def test_every_collection_exists_with_its_indexes(db: Database[dict[str, Any]]) -> None:
    ensure_indexes(db)
    assert set(COLLECTIONS) <= set(db.list_collection_names())
    for collection, specs in INDEXES.items():
        assert len(keys(db, collection)) == len(specs), collection


def test_ensure_indexes_is_idempotent(db: Database[dict[str, Any]]) -> None:
    ensure_indexes(db)
    before = {c: keys(db, c) for c in COLLECTIONS}
    ensure_indexes(db)
    assert {c: keys(db, c) for c in COLLECTIONS} == before


def test_every_tenant_collection_index_starts_with_tenant_id(db: Database[dict[str, Any]]) -> None:
    # A query always carries tenant_id first (TenantRepo), so an index that does not start with it is either unused
    # or a sign of a query that is not tenant-scoped. TTL indexes are the exception: MongoDB requires them to have a
    # single field, and they serve the server's own expiry, not queries.
    ensure_indexes(db)
    for collection in set(COLLECTIONS) - set(SYSTEM_COLLECTIONS):
        for name, info in db[collection].index_information().items():
            if name == "_id_" or "expireAfterSeconds" in info:
                continue
            assert next(iter(info["key"]))[0] == "tenant_id", f"{collection}.{name}"


def test_idempotency_records_expire_after_24_hours(db: Database[dict[str, Any]]) -> None:
    ensure_indexes(db)
    ttl = [info for info in db.idempotency_keys.index_information().values() if "expireAfterSeconds" in info]
    assert [(list(i["key"]), i["expireAfterSeconds"]) for i in ttl] == [([("created_at", 1)], 86_400)]


@pytest.mark.parametrize(
    ("collection", "fields"),
    [
        ("users", ["tenant_id", "email"]),
        ("identities", ["issuer", "subject"]),
        ("identities", ["tenant_id", "email"]),
        ("stage_runs", ["tenant_id", "recording_id", "stage", "version", "attempt"]),
        ("analyses", ["tenant_id", "recording_id", "version"]),
        ("idempotency_keys", ["tenant_id", "route", "key"]),
    ],
)
def test_unique_indexes_that_protect_invariants(
    db: Database[dict[str, Any]], collection: str, fields: list[str]
) -> None:
    ensure_indexes(db)
    found = [(f, unique) for f, unique in keys(db, collection).values() if [name for name, _ in f] == fields]
    assert found and found[0][1], f"{collection} needs a unique index on {fields}"


def test_identities_unique_subject_ignores_pending_invites(db: Database[dict[str, Any]]) -> None:
    # Invites have no subject until first login; many pending invites must not collide on subject=None.
    ensure_indexes(db)
    db.identities.insert_many(
        [
            {"_id": "i1", "tenant_id": "t1", "issuer": "https://idp", "email": "a@x.com", "user_id": "u1"},
            {"_id": "i2", "tenant_id": "t1", "issuer": "https://idp", "email": "b@x.com", "user_id": "u2"},
        ]
    )
    assert db.identities.count_documents({}) == 2


def test_outbox_has_an_index_for_the_relays_unpublished_scan(db: Database[dict[str, Any]]) -> None:
    ensure_indexes(db)
    fields = [[name for name, _ in f] for f, _ in keys(db, "outbox").values()]
    assert ["published_at", "created_at"] in fields


def test_async_variant_creates_the_same_indexes(mongo_uri: str, db: Database[dict[str, Any]]) -> None:
    async def run() -> None:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
        try:
            await ensure_indexes_async(client[db.name])
            await ensure_indexes_async(client[db.name])  # idempotent
        finally:
            await client.close()

    asyncio.run(run())
    for collection, specs in INDEXES.items():
        assert len(keys(db, collection)) == len(specs), collection
