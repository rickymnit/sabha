"""tenant_repo: routes get repositories bound to the caller's tenant (P1.6). Uses a real MongoDB replica set.

Authentication is replaced with a fixed principal here (its own tests are in test_auth.py); the tenant scoping under
test is the real repository's.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient

from sabha_api.auth import Principal, Role, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.main import ResourcesFactory
from sabha_api.resources import Resources
from sabha_core.models import Person
from sabha_core.repo import CollectionNotAllowedError, TenantRepo
from sabha_core.settings import Settings

pytestmark = pytest.mark.integration


async def ok() -> object:
    return None


@pytest.fixture
def db_name(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[str]:
    name = f"deps_{uuid.uuid4().hex[:12]}"
    mongo_replica_set[name].people.insert_many(
        [
            {"_id": "a1", "tenant_id": "tenant-a", "name": "Asha"},
            {"_id": "b1", "tenant_id": "tenant-b", "name": "Bina"},
            {"_id": "b2", "tenant_id": "tenant-b", "name": "Bharat"},
        ]
    )
    yield name
    mongo_replica_set.drop_database(name)


def mongo_resources(mongo_uri: str, db_name: str) -> ResourcesFactory:
    @asynccontextmanager
    async def factory(_: Settings) -> AsyncIterator[Resources]:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri, tz_aware=True)
        try:
            yield Resources(readiness={"mongo": ok}, mongo=client, db=client[db_name])
        finally:
            await client.close()

    return factory


def as_tenant(app: FastAPI, tenant_id: str) -> None:
    app.dependency_overrides[current_principal] = lambda: Principal("u1", tenant_id, Role.STAFF, ())


def add_people_route(app: FastAPI) -> None:
    @app.get("/v1/test/people")
    async def people(repo: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]) -> list[str]:
        return sorted(p.id for p in await repo.find({}))

    @app.get("/v1/test/people/{person_id}")
    async def person(
        person_id: str, repo: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
    ) -> dict[str, Any]:
        found = await repo.find_one({"_id": person_id})
        return {"found": found is not None}


def test_each_tenant_sees_only_its_own_documents(make_client: Any, mongo_uri: str, db_name: str) -> None:
    client: TestClient = make_client(resources=mongo_resources(mongo_uri, db_name))
    app = client.app
    assert isinstance(app, FastAPI)
    add_people_route(app)

    as_tenant(app, "tenant-a")
    assert client.get("/v1/test/people").json() == ["a1"]
    assert client.get("/v1/test/people/b1").json() == {"found": False}

    as_tenant(app, "tenant-b")
    assert client.get("/v1/test/people").json() == ["b1", "b2"]


def test_without_a_database_routes_answer_503(make_client: Any) -> None:
    client: TestClient = make_client()  # fake resources: no MongoDB
    app = client.app
    assert isinstance(app, FastAPI)
    add_people_route(app)
    as_tenant(app, "tenant-a")
    response = client.get("/v1/test/people")
    assert response.status_code == 503 and response.json()["code"] == "not_ready"


@pytest.mark.parametrize("collection", ["tenants", "nope"])
def test_collection_names_are_checked_when_the_route_is_defined(collection: str) -> None:
    with pytest.raises(CollectionNotAllowedError):
        tenant_repo(collection, Person)
