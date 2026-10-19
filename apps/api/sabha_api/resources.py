"""Clients the API holds for its whole life: one MongoDB client, one Redis client and one S3 client.

They are created when the app starts (sabha_api.main lifespan) and closed when it stops. Requests reach them through
`request.app.state.resources`; data access still goes through the tenant-scoped repository (golden rule 1, P1.6):
routes get repositories from sabha_api.deps, never `db` itself.

At start-up a background task creates every missing collection and index (sabha_core.indexes), retrying with backoff
while MongoDB is unreachable. The API starts either way (GET /health must not depend on the database), but the
`indexes` readiness check fails until the task has succeeded, so GET /ready keeps traffic away from an API whose
unique indexes do not exist yet.

`readiness` maps each dependency to a check used by GET /ready. Each check raises on failure and is bounded by the
caller's timeout.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.config import Config
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from redis.asyncio import Redis

from sabha_core.indexes import ensure_indexes_async
from sabha_core.settings import Settings

Check = Callable[[], Awaitable[object]]

# Connection timeouts for the clients themselves; GET /ready adds its own overall bound per check.
_CONNECT_TIMEOUT_S = 2.0
_INDEX_RETRY_MAX_S = 60.0

log = logging.getLogger("sabha.api.resources")


@dataclass(frozen=True, slots=True)
class Resources:
    readiness: Mapping[str, Check]
    mongo: AsyncMongoClient[dict[str, Any]] | None = None
    db: AsyncDatabase[dict[str, Any]] | None = None  # settings.mongo_db; reached only through sabha_api.deps
    redis: Redis | None = None
    s3: Any = field(default=None)  # boto3 S3 client (boto3 has no type information)


def s3_client(settings: Settings) -> Any:
    keys = (
        {
            "aws_access_key_id": settings.s3_access_key_id.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_access_key.get_secret_value(),
        }
        if settings.s3_access_key_id is not None and settings.s3_secret_access_key is not None
        else {}  # on AWS the IAM role provides credentials
    )
    config = Config(
        connect_timeout=_CONNECT_TIMEOUT_S,
        read_timeout=10,
        retries={"max_attempts": 2, "mode": "standard"},
        s3={"addressing_style": "path"} if settings.s3_endpoint_url else {},
    )
    return boto3.client(
        "s3", region_name=settings.s3_region, endpoint_url=settings.s3_endpoint_url, config=config, **keys
    )


async def _create_indexes(db: AsyncDatabase[dict[str, Any]], done: asyncio.Event) -> None:
    delay = 1.0
    while True:
        try:
            await ensure_indexes_async(db)
        except PyMongoError as exc:
            log.warning("could not create indexes; retrying in %.0f s", delay, extra={"error_type": type(exc).__name__})
            await asyncio.sleep(delay)
            delay = min(delay * 2, _INDEX_RETRY_MAX_S)
        else:
            done.set()
            return


@asynccontextmanager
async def open_resources(settings: Settings) -> AsyncIterator[Resources]:
    mongo: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        settings.mongo_uri.get_secret_value(), connectTimeoutMS=int(_CONNECT_TIMEOUT_S * 1000), tz_aware=True
    )
    redis = Redis.from_url(settings.redis_url.get_secret_value(), socket_connect_timeout=_CONNECT_TIMEOUT_S)
    s3 = s3_client(settings)
    db = mongo[settings.mongo_db]

    async def check_mongo() -> object:
        return await mongo.admin.command("ping")

    async def check_redis() -> object:
        return await redis.ping()

    async def check_storage() -> object:
        # The buckets requests use directly; backups are written by a scheduled job, not the API.
        for bucket in (settings.s3_bucket_audio, settings.s3_bucket_artefacts):
            await asyncio.to_thread(s3.head_bucket, Bucket=bucket)
        return None

    indexes_ready = asyncio.Event()
    indexing = asyncio.create_task(_create_indexes(db, indexes_ready))

    async def check_indexes() -> object:
        if not indexes_ready.is_set():
            raise RuntimeError("collections and indexes are not created yet")
        return None

    try:
        yield Resources(
            readiness={"mongo": check_mongo, "redis": check_redis, "storage": check_storage, "indexes": check_indexes},
            mongo=mongo,
            db=db,
            redis=redis,
            s3=s3,
        )
    finally:
        indexing.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await indexing
        await redis.aclose()
        await mongo.close()
        s3.close()
