"""Golden rule 1: tenant A can never read, change, delete or aggregate tenant B's documents (plan task P1.6).

Every test runs twice: against TenantRepo (async, used by the API) and SyncTenantRepo (used by Celery workers),
through the same small interface, so the two implementations cannot drift apart.

Each test starts with the same data in a fresh database: three people in tenant A and two in tenant B.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pymongo import AsyncMongoClient, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from sabha_core.models import Person, TenantDoc
from sabha_core.repo import (
    MissingTenantError,
    SyncTenantRepo,
    TenantRepo,
    TenantViolationError,
    UnsafePipelineError,
)

pytestmark = pytest.mark.integration

A, B = "tenant-a", "tenant-b"


class AsyncRepoAdapter:
    """Runs each TenantRepo coroutine to completion on one event loop, so tests can call it like the sync repo."""

    def __init__(self, repo: TenantRepo[Any], loop: asyncio.AbstractEventLoop) -> None:
        self._repo = repo
        self._loop = loop

    def __getattr__(self, name: str) -> Callable[..., Any]:
        method = getattr(self._repo, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            return self._loop.run_until_complete(method(*args, **kwargs))

        return call


MakeRepo = Callable[[str], Any]


@pytest.fixture
def db_name(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"iso_{uuid.uuid4().hex[:12]}"
    yield name
    mongo_replica_set.drop_database(name)


@pytest.fixture
def raw(mongo_replica_set: MongoClient[dict[str, Any]], db_name: str) -> Database[dict[str, Any]]:
    """Direct database access, for seeding and checking only. Product code may never do this (golden rule 1)."""
    return mongo_replica_set[db_name]


@pytest.fixture(params=["async", "sync"])
def make_repo(
    request: pytest.FixtureRequest, mongo_uri: str, mongo_replica_set: MongoClient[dict[str, Any]], db_name: str
) -> Iterator[MakeRepo]:
    """`make_repo(tenant_id)` returns a repo over `people` bound to that tenant."""
    if request.param == "sync":
        yield lambda tenant_id: SyncTenantRepo(mongo_replica_set[db_name], "people", tenant_id, Person)
        return
    loop = asyncio.new_event_loop()
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri)
    try:
        yield lambda tenant_id: AsyncRepoAdapter(TenantRepo(client[db_name], "people", tenant_id, Person), loop)
    finally:
        loop.run_until_complete(client.close())
        loop.close()


@pytest.fixture(autouse=True)
def seed(raw: Database[dict[str, Any]]) -> None:
    raw.people.insert_many(
        [
            {"_id": "a1", "tenant_id": A, "name": "Asha", "unit_id": "u-a"},
            {"_id": "a2", "tenant_id": A, "name": "Arjun", "unit_id": "u-a"},
            {"_id": "a3", "tenant_id": A, "name": "Anil", "unit_id": "u-a2"},
            {"_id": "b1", "tenant_id": B, "name": "Bina", "unit_id": "u-b"},
            {"_id": "b2", "tenant_id": B, "name": "Bharat", "unit_id": "u-b"},
        ]
    )


def b_docs(raw: Database[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(raw.people.find({"tenant_id": B}), key=lambda d: d["_id"])


B_BEFORE = [
    {"_id": "b1", "tenant_id": B, "name": "Bina", "unit_id": "u-b"},
    {"_id": "b2", "tenant_id": B, "name": "Bharat", "unit_id": "u-b"},
]


# --- Construction ---


@pytest.mark.parametrize("tenant_id", ["", "   ", None])
def test_a_repo_cannot_be_built_without_a_tenant(make_repo: MakeRepo, tenant_id: Any) -> None:
    with pytest.raises(MissingTenantError):
        make_repo(tenant_id)


# --- Reads ---


def test_find_sees_only_own_tenant(make_repo: MakeRepo) -> None:
    assert sorted(p.id for p in make_repo(A).find({})) == ["a1", "a2", "a3"]
    assert sorted(p.id for p in make_repo(B).find({})) == ["b1", "b2"]


def test_find_one_by_another_tenants_id_returns_nothing(make_repo: MakeRepo) -> None:
    assert make_repo(A).find_one({"_id": "b1"}) is None


def test_count_counts_only_own_tenant(make_repo: MakeRepo) -> None:
    assert make_repo(A).count({}) == 3
    assert make_repo(A).count({"_id": {"$in": ["a1", "b1", "b2"]}}) == 1


def test_or_filter_cannot_reach_another_tenant(make_repo: MakeRepo) -> None:
    found = make_repo(A).find({"$or": [{"_id": "b1"}, {"name": "Bharat"}, {"unit_id": "u-a2"}]})
    assert [p.id for p in found] == ["a3"]


def test_filter_naming_another_tenant_is_refused(make_repo: MakeRepo) -> None:
    with pytest.raises(TenantViolationError):
        make_repo(A).find({"tenant_id": B})


@pytest.mark.parametrize(
    "smuggled",
    [
        {"tenant_id": {"$in": [A, B]}},
        {"tenant_id": {"$ne": A}},
        {"$or": [{"tenant_id": B}]},
        {"$and": [{"_id": "b1"}, {"tenant_id": {"$exists": True}}]},
        {"$expr": {"$eq": ["$tenant_id", B]}},
        {"$where": "this.tenant_id == 'tenant-b'"},
    ],
)
def test_any_filter_mentioning_tenant_id_or_running_code_is_refused(make_repo: MakeRepo, smuggled: Any) -> None:
    with pytest.raises(TenantViolationError):
        make_repo(A).find(smuggled)


# --- Writes ---


def test_insert_stamps_the_repos_tenant(make_repo: MakeRepo, raw: Database[dict[str, Any]]) -> None:
    inserted = make_repo(A).insert_one(Person(name="Aditi"))
    assert inserted.tenant_id == A
    assert raw.people.find_one({"_id": inserted.id}, {"_id": 0, "tenant_id": 1}) == {"tenant_id": A}


def test_insert_of_a_document_for_another_tenant_is_refused(make_repo: MakeRepo, raw: Database[dict[str, Any]]) -> None:
    with pytest.raises(TenantViolationError):
        make_repo(A).insert_one(Person(tenant_id=B, name="Intruder"))
    assert raw.people.count_documents({"name": "Intruder"}) == 0


def test_insert_many_refuses_the_whole_batch_if_one_document_is_foreign(
    make_repo: MakeRepo, raw: Database[dict[str, Any]]
) -> None:
    with pytest.raises(TenantViolationError):
        make_repo(A).insert_many([Person(name="Ok"), Person(tenant_id=B, name="Intruder")])
    assert raw.people.count_documents({"name": {"$in": ["Ok", "Intruder"]}}) == 0


def test_update_one_cannot_touch_another_tenants_document(make_repo: MakeRepo, raw: Database[dict[str, Any]]) -> None:
    assert make_repo(A).update_one({"_id": "b1"}, {"$set": {"name": "Hacked"}}) == 0
    assert b_docs(raw) == B_BEFORE


def test_update_many_with_an_empty_filter_changes_only_own_tenant(
    make_repo: MakeRepo, raw: Database[dict[str, Any]]
) -> None:
    assert make_repo(A).update_many({}, {"$set": {"unit_id": "moved"}}) == 3
    assert b_docs(raw) == B_BEFORE


def test_reusing_another_tenants_id_changes_nothing_of_theirs(
    make_repo: MakeRepo, raw: Database[dict[str, Any]]
) -> None:
    # /tenant-check finding 2. _id is unique across the whole collection, so writing tenant B's id from tenant A
    # fails with DuplicateKeyError. B's document is untouched, but the error shows the id exists somewhere: this is
    # why clients never choose ids (the server generates them; see the sabha_core.repo docstring).
    repo = make_repo(A)
    with pytest.raises(DuplicateKeyError):
        repo.insert_one(Person(id="b1", name="Intruder"))
    with pytest.raises(DuplicateKeyError):
        repo.update_one({"_id": "b1"}, {"$set": {"name": "Hacked"}}, upsert=True)
    assert b_docs(raw) == B_BEFORE


def test_upsert_creates_the_document_in_own_tenant(make_repo: MakeRepo, raw: Database[dict[str, Any]]) -> None:
    # Upserting tenant B's id from tenant A must not modify B's document; it creates A's own.
    make_repo(A).update_one({"_id": "new"}, {"$set": {"name": "Upserted"}}, upsert=True)
    assert raw.people.find_one({"_id": "new"}) == {"_id": "new", "tenant_id": A, "name": "Upserted"}
    assert b_docs(raw) == B_BEFORE


@pytest.mark.parametrize(
    "update",
    [
        {"$set": {"tenant_id": B}},
        {"$set": {"tenant_id.x": 1}},
        {"$unset": {"tenant_id": ""}},
        {"$rename": {"tenant_id": "old_tenant"}},
        {"$rename": {"name": "tenant_id"}},
        {"$setOnInsert": {"tenant_id": B}},
        {"name": "replacement document, not an update"},
        [{"$set": {"tenant_id": B}}],
        [{"$set": {"name": "pipeline updates are refused outright"}}],
    ],
)
def test_updates_can_never_change_tenant_id(make_repo: MakeRepo, raw: Database[dict[str, Any]], update: Any) -> None:
    repo = make_repo(A)
    with pytest.raises(TenantViolationError):
        repo.update_one({"_id": "a1"}, update)
    with pytest.raises(TenantViolationError):
        repo.update_many({}, update)
    assert raw.people.count_documents({"tenant_id": A}) == 3


def test_delete_one_cannot_remove_another_tenants_document(make_repo: MakeRepo, raw: Database[dict[str, Any]]) -> None:
    assert make_repo(A).delete_one({"_id": "b1"}) == 0
    assert b_docs(raw) == B_BEFORE


def test_delete_many_with_an_empty_filter_removes_only_own_tenant(
    make_repo: MakeRepo, raw: Database[dict[str, Any]]
) -> None:
    assert make_repo(A).delete_many({}) == 3
    assert raw.people.count_documents({"tenant_id": A}) == 0
    assert b_docs(raw) == B_BEFORE


# --- Aggregation ---


def test_aggregate_sees_only_own_tenant(make_repo: MakeRepo) -> None:
    rows = make_repo(A).aggregate([{"$group": {"_id": None, "n": {"$sum": 1}}}])
    assert rows == [{"_id": None, "n": 3}]


def test_aggregate_with_an_empty_pipeline_still_filters(make_repo: MakeRepo) -> None:
    assert sorted(row["_id"] for row in make_repo(A).aggregate([])) == ["a1", "a2", "a3"]


def test_a_match_stage_cannot_widen_the_tenant_filter(make_repo: MakeRepo) -> None:
    with pytest.raises(TenantViolationError):
        make_repo(A).aggregate([{"$match": {"tenant_id": {"$in": [A, B]}}}])


@pytest.mark.parametrize(
    "stage",
    [
        {"$lookup": {"from": "people", "localField": "unit_id", "foreignField": "unit_id", "as": "x"}},
        {"$unionWith": {"coll": "people"}},
        {
            "$graphLookup": {
                "from": "people",
                "startWith": "$_id",
                "connectFromField": "_id",
                "connectToField": "_id",
                "as": "x",
            }
        },
        {"$out": "stolen"},
        {"$merge": {"into": "stolen"}},
        {"$facet": {"inner": [{"$unionWith": {"coll": "people"}}]}},
        {"$documents": [{"tenant_id": B}]},
        {"$collStats": {"count": {}}},
        {"$currentOp": {}},
        {"$listSessions": {}},
        {"$changeStream": {}},
    ],
)
def test_stages_that_read_or_write_outside_the_filtered_collection_are_refused(
    make_repo: MakeRepo, raw: Database[dict[str, Any]], stage: dict[str, Any]
) -> None:
    with pytest.raises(UnsafePipelineError):
        make_repo(A).aggregate([stage])
    assert "stolen" not in raw.list_collection_names()


def test_stages_cannot_set_or_rewrite_tenant_id_before_a_later_match(make_repo: MakeRepo) -> None:
    # The tenant $match comes first, so later stages cannot change which documents it saw, but a pipeline that
    # rewrites tenant_id is a bug or an attack either way.
    for stage in (
        {"$set": {"tenant_id": B}},
        {"$addFields": {"tenant_id": B}},
        {"$project": {"tenant_id": {"$literal": B}}},
        {"$replaceRoot": {"newRoot": {"tenant_id": B}}},
        {"$replaceWith": {"tenant_id": B}},
    ):
        with pytest.raises(TenantViolationError):
            make_repo(A).aggregate([stage])


# --- Every method is covered ---


def test_this_file_covers_every_public_repo_method() -> None:
    """A new repo method must get an isolation test here before it can ship."""
    covered = {
        "find", "find_one", "count", "insert_one", "insert_many", "update_one", "update_many",
        "delete_one", "delete_many", "aggregate",
    }  # fmt: skip
    for repo_class in (TenantRepo, SyncTenantRepo):
        public = {name for name in vars(repo_class) if not name.startswith("_") and callable(getattr(repo_class, name))}
        assert public == covered, f"{repo_class.__name__}: add isolation tests for {sorted(public - covered)}"


def test_tenant_doc_models_carry_tenant_id() -> None:
    assert "tenant_id" in TenantDoc.model_fields
