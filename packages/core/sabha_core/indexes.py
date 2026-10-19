"""Every collection and its indexes, created idempotently when the API or a worker starts (plan task P1.6).

In tenant collections every index starts with tenant_id, because every query the repository runs does
(sabha_core.repo). Unique indexes protect invariants: one user per email in a tenant, one stage run per
(recording, stage, version, attempt), one analysis per (recording, version), one login per (issuer, subject).

Running `ensure_indexes` again changes nothing; an index whose definition changed under the same name makes MongoDB
raise, which is what we want: changing an index is a deliberate migration.
"""

from __future__ import annotations

import contextlib
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from sabha_core.repo import COLLECTIONS

T = "tenant_id"
IDEMPOTENCY_TTL_S = 24 * 3600  # CLAUDE.md: replays within 24 h return the original response


def _ix(name: str, *keys: tuple[str, int], unique: bool = False, **options: Any) -> IndexModel:
    return IndexModel(list(keys), name=name, unique=unique, **options)


INDEXES: dict[str, list[IndexModel]] = {
    "tenants": [],
    "units": [_ix("tenant_parent", (T, ASCENDING), ("parent_id", ASCENDING))],
    "users": [
        _ix("tenant_email", (T, ASCENDING), ("email", ASCENDING), unique=True),
        _ix("tenant_role", (T, ASCENDING), ("role", ASCENDING)),
    ],
    "people": [
        _ix("tenant_unit", (T, ASCENDING), ("unit_id", ASCENDING)),
        _ix("tenant_user", (T, ASCENDING), ("user_id", ASCENDING)),
    ],
    "recordings": [
        _ix("tenant_status_created", (T, ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)),
        _ix("tenant_person_created", (T, ASCENDING), ("person_id", ASCENDING), ("created_at", DESCENDING)),
        _ix("tenant_sha256", (T, ASCENDING), ("sha256", ASCENDING)),  # duplicate detection (P2.2)
    ],
    "stage_runs": [
        _ix(
            "tenant_recording_stage_version_attempt",
            (T, ASCENDING),
            ("recording_id", ASCENDING),
            ("stage", ASCENDING),
            ("version", ASCENDING),
            ("attempt", ASCENDING),
            unique=True,
        )
    ],
    "transcripts": [_ix("tenant_recording", (T, ASCENDING), ("recording_id", ASCENDING))],
    "rubrics": [_ix("tenant_rubric", (T, ASCENDING), ("rubric_id", ASCENDING), unique=True)],
    "analyses": [
        _ix(
            "tenant_recording_version",
            (T, ASCENDING),
            ("recording_id", ASCENDING),
            ("version", ASCENDING),
            unique=True,
        )
    ],
    "scores": [
        _ix("tenant_analysis", (T, ASCENDING), ("analysis_id", ASCENDING)),
        _ix("tenant_person_created", (T, ASCENDING), ("person_id", ASCENDING), ("created_at", DESCENDING)),
    ],
    "disputes": [
        _ix("tenant_status_created", (T, ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)),
        _ix("tenant_analysis", (T, ASCENDING), ("analysis_id", ASCENDING)),
    ],
    "usage_events": [_ix("tenant_occurred", (T, ASCENDING), ("occurred_at", ASCENDING))],
    "audit_log": [_ix("tenant_at", (T, ASCENDING), ("at", DESCENDING))],
    "llm_calls": [
        _ix("tenant_created", (T, ASCENDING), ("created_at", DESCENDING)),
        _ix("tenant_recording", (T, ASCENDING), ("recording_id", ASCENDING)),
    ],
    "idempotency_keys": [
        _ix("tenant_route_key", (T, ASCENDING), ("route", ASCENDING), ("key", ASCENDING), unique=True),
        # TTL indexes must have a single field; MongoDB deletes expired records itself (no query involved).
        _ix("expiry", ("created_at", ASCENDING), expireAfterSeconds=IDEMPOTENCY_TTL_S),
    ],
    # System collections (sabha_core.repo.SYSTEM_COLLECTIONS): read across tenants by the relay and by login.
    "outbox": [
        _ix("unpublished", ("published_at", ASCENDING), ("created_at", ASCENDING)),
        _ix("tenant_created", (T, ASCENDING), ("created_at", ASCENDING)),
    ],
    "identities": [
        # Pending invites have no subject yet; only linked logins must be unique.
        _ix(
            "issuer_subject",
            ("issuer", ASCENDING),
            ("subject", ASCENDING),
            unique=True,
            partialFilterExpression={"subject": {"$type": "string"}},
        ),
        _ix("tenant_email", (T, ASCENDING), ("email", ASCENDING), unique=True),  # one invite per email per tenant
        _ix("email", ("email", ASCENDING)),  # login finds a first-time user's invites by email
    ],
}

if set(INDEXES) != set(COLLECTIONS):  # pragma: no cover - a module-level consistency check
    raise RuntimeError("INDEXES and sabha_core.repo.COLLECTIONS must list the same collections")


def ensure_indexes(db: Database[dict[str, Any]]) -> None:
    """Create every collection and index that does not exist yet. Safe to call on every start."""
    existing = set(db.list_collection_names())
    for collection, indexes in INDEXES.items():
        if collection not in existing:
            with contextlib.suppress(CollectionInvalid):  # another process created it first
                db.create_collection(collection)
        if indexes:
            db[collection].create_indexes(indexes)


async def ensure_indexes_async(db: AsyncDatabase[dict[str, Any]]) -> None:
    """`ensure_indexes` for the API's async client: run once when the API starts."""
    existing = set(await db.list_collection_names())
    for collection, indexes in INDEXES.items():
        if collection not in existing:
            with contextlib.suppress(CollectionInvalid):  # another process created it first
                await db.create_collection(collection)
        if indexes:
            await db[collection].create_indexes(indexes)
