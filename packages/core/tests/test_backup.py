"""Backup and restore drill (P7.3): what is exported comes back the same, and only into a scratch database."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.backup import export_backup, latest_backup, restore_drill
from sabha_core.models import Person, Recording, Tenant, utc_now
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan

pytestmark = pytest.mark.integration
BUCKET = "sabha-backups"


@pytest.fixture
def db(mongo_replica_set: MongoClient[dict[str, Any]]) -> Iterator[Database[dict[str, Any]]]:
    name = f"backup_{uuid.uuid4().hex[:12]}"
    yield mongo_replica_set[name]
    mongo_replica_set.drop_database(name)


def test_a_backup_restores_into_a_scratch_database_unchanged(
    db: Database[dict[str, Any]], mongo_replica_set: MongoClient[dict[str, Any]], s3_storage: Any
) -> None:
    s3 = s3_storage.client()
    db.tenants.insert_one(
        Tenant.from_profile("school", name="Sunrise", plan=Plan.PILOT, id="t1").model_dump(by_alias=True)
    )
    db.people.insert_one(Person(tenant_id="t1", name="Asha", unit_id="u1").model_dump(by_alias=True))
    for _ in range(3):
        db.recordings.insert_one(Recording(tenant_id="t1", type=ConversationType.TEACHING).model_dump(by_alias=True))
    db.idempotency_keys.insert_one({"_id": "k", "tenant_id": "t1"})  # left out: lives 24 hours

    manifest = export_backup(db, s3, BUCKET, now=utc_now())
    assert manifest["collections"]["recordings"]["count"] == 3
    assert "idempotency_keys" not in manifest["collections"]

    day = latest_backup(s3, BUCKET)
    target = f"restore_drill_{uuid.uuid4().hex[:8]}"
    try:
        report = restore_drill(mongo_replica_set, s3, BUCKET, day=day, target=target)
        assert report.passed, report.problems
        assert (report.collections["tenants"], report.collections["recordings"]) == (1, 3)
        original = db.recordings.find_one({}, sort=[("_id", 1)])
        assert mongo_replica_set[target].recordings.find_one({"_id": original["_id"]}) == original  # type: ignore[index]
    finally:
        mongo_replica_set.drop_database(target)
    with pytest.raises(ValueError, match="restore_drill_"):
        restore_drill(mongo_replica_set, s3, BUCKET, day=day, target=db.name)  # never the live database
