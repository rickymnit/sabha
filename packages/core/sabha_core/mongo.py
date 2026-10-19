"""Opening the synchronous MongoDB connection for workers, the relay and scripts (one place, golden rule 1).

Returns the client (to close and to start transactions) and the database handle, which callers hand to the
tenant-scoped repositories (sabha_core.repo); nothing here reads documents.
"""

from __future__ import annotations

from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.settings import Settings


def open_sync(settings: Settings) -> tuple[MongoClient[dict[str, Any]], Database[dict[str, Any]]]:
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    return client, client.get_database(settings.mongo_db)
