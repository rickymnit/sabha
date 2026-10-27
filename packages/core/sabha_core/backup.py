"""Database backups to the backups bucket, and the restore drill (plan task P7.3).

A second copy next to Atlas continuous backup (turned on with the AWS setup, docs/runbook.md): every night each
collection is written as gzipped extended-JSON lines (bson.json_util, so ids, dates and types survive) under
mongo/{date}/{collection}.jsonl.gz, with a manifest.json of counts and SHA-256 sums. idempotency_keys are left out:
they live 24 hours. How long backups are kept is the bucket's lifecycle rule (infrastructure).

The restore drill loads a backup into a scratch database (its name must start with RESTORE_PREFIX, so the live
database can never be the target), then checks each collection's count against the manifest and a sample of
documents against the backup file. Reading whole collections across tenants is why this module is in
tests/security/test_raw_collection_access.py's allow-list; it only reads the live database.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bson import json_util
from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.repo import COLLECTIONS

PREFIX = "mongo/"
RESTORE_PREFIX = "restore_drill_"
SKIPPED = frozenset({"idempotency_keys"})  # 24-hour replay records
SAMPLE = 5


def backup_prefix(day: str) -> str:
    return f"{PREFIX}{day}/"


def export_backup(db: Database[dict[str, Any]], s3: Any, bucket: str, *, now: datetime) -> dict[str, Any]:
    """Write every collection and the manifest for `now`'s date; returns the manifest."""
    day = now.strftime("%Y-%m-%d")
    manifest: dict[str, Any] = {"created_at": now.isoformat(), "database": db.name, "collections": {}}
    for name in sorted(set(COLLECTIONS) - SKIPPED):
        buffer = io.BytesIO()
        count = 0
        with gzip.GzipFile(fileobj=buffer, mode="wb") as out:
            for doc in db[name].find({}, sort=[("_id", 1)]):
                out.write(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS).encode() + b"\n")
                count += 1
        body = buffer.getvalue()
        s3.put_object(Bucket=bucket, Key=f"{backup_prefix(day)}{name}.jsonl.gz", Body=body,
                      ContentType="application/gzip")  # fmt: skip
        manifest["collections"][name] = {"count": count, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    s3.put_object(Bucket=bucket, Key=f"{backup_prefix(day)}manifest.json", Body=json.dumps(manifest, indent=2).encode(),
                  ContentType="application/json")  # fmt: skip
    return manifest


def latest_backup(s3: Any, bucket: str) -> str:
    """The date of the newest backup with a manifest."""
    days: list[str] = sorted(
        str(obj["Key"]).removeprefix(PREFIX).split("/")[0]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX)
        for obj in page.get("Contents", [])
        if obj["Key"].endswith("/manifest.json")
    )
    if not days:
        raise LookupError(f"no backup in {bucket}")
    return days[-1]


@dataclass
class DrillReport:
    day: str
    target: str
    collections: dict[str, int] = field(default_factory=dict)  # restored counts
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def restore_drill(client: MongoClient[dict[str, Any]], s3: Any, bucket: str, *, day: str, target: str) -> DrillReport:
    """Restore `day`'s backup into the scratch database `target` and check it."""
    if not target.startswith(RESTORE_PREFIX):
        raise ValueError(f"a restore drill writes only to a database named {RESTORE_PREFIX}*, not {target!r}")
    scratch = client[target]
    report = DrillReport(day, target)
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=f"{backup_prefix(day)}manifest.json")["Body"].read())
    for name, expected in manifest["collections"].items():
        body = s3.get_object(Bucket=bucket, Key=f"{backup_prefix(day)}{name}.jsonl.gz")["Body"].read()
        if hashlib.sha256(body).hexdigest() != expected["sha256"]:
            report.problems.append(f"{name}: the file does not match its checksum")
            continue
        docs = [json_util.loads(line) for line in gzip.decompress(body).splitlines() if line]
        scratch[name].drop()
        if docs:
            scratch[name].insert_many(docs)
        restored = scratch[name].count_documents({})
        report.collections[name] = restored
        if restored != expected["count"]:
            report.problems.append(f"{name}: {restored} documents restored, the backup has {expected['count']}")
        for doc in random.sample(docs, min(SAMPLE, len(docs))):
            if scratch[name].find_one({"_id": doc["_id"]}) != doc:
                report.problems.append(f"{name}: document {doc['_id']} differs after the restore")
    return report
