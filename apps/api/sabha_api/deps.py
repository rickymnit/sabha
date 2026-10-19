"""Request dependencies that give routes data access scoped to the caller's tenant (golden rule 1, plan task P1.6).

    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]

The repository is bound to the signed-in principal's tenant_id, so a route cannot read or write another tenant's
documents whatever ids a request carries: a recording id from another tenant simply is not found (404). Routes
never touch the database handle itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase

from sabha_api.auth import Principal, current_principal
from sabha_api.errors import NotReadyError
from sabha_core.models import TenantDoc
from sabha_core.repo import TenantRepo, check_tenant_collection


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
