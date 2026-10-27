"""Request dependencies that give routes data access scoped to the caller's tenant (golden rule 1, plan task P1.6).

    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]

The repository is bound to the signed-in principal's tenant_id, so a route cannot read or write another tenant's
documents whatever ids a request carries: a recording id from another tenant simply is not found (404). Routes
never touch the database handle itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, Request
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from sabha_api.auth import Principal, current_principal
from sabha_api.errors import NotReadyError
from sabha_core.models import TenantDoc
from sabha_core.repo import OwnTenantRepo, TenantRepo, check_tenant_collection


def _database(request: Request) -> AsyncDatabase[dict[str, Any]]:
    db: AsyncDatabase[dict[str, Any]] | None = request.app.state.resources.db
    if db is None:
        raise NotReadyError("The database is not available.")
    return db


def tenant_repo[T: TenantDoc](collection: str, model: type[T]) -> Callable[..., Awaitable[TenantRepo[T]]]:
    """A dependency returning a TenantRepo over `collection` for the caller's tenant. Checks the name at import."""
    check_tenant_collection(collection)

    async def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
        db: Annotated[AsyncDatabase[dict[str, Any]], Depends(_database)],
    ) -> TenantRepo[T]:
        return TenantRepo(db, collection, principal.tenant_id, model)

    return dependency


async def own_tenant_repo(
    principal: Annotated[Principal, Depends(current_principal)],
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(_database)],
) -> OwnTenantRepo:
    """The caller's own tenant record, for the settings routes (P1.7)."""
    return OwnTenantRepo(db, principal.tenant_id)


class Transactions:
    """Runs several repository writes in one MongoDB transaction: pass `session` to each repo call."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._client = db.client

    @asynccontextmanager
    async def run(self) -> AsyncIterator[AsyncClientSession]:
        async with self._client.start_session() as session, await session.start_transaction():
            yield session


def transactions(db: Annotated[AsyncDatabase[dict[str, Any]], Depends(_database)]) -> Transactions:
    return Transactions(db)
