"""Reviewer corrections of speaker roles, against what Sabha decided by itself (owner's decision, 2026-11-04).

    uv run python eval/role_corrections.py [--type support] [--out eval/reports/role-corrections-<date>.jsonl]

When roles are unclear, a reviewer says which speaker is the staff member (ADR 0007, `recording.confirmed_roles`).
The transcribe stage keeps its own decision in `roles_auto@v1.json`, and for types with an evidence profile what it
found in `role_evidence@v1.json`; a reviewer's confirmation never overwrites them. This lists, per recording with
confirmed roles: the automatic staff speaker and how it was decided, the reviewer's, whether they agree, and the
evidence. Those rows are the labelled data for tuning the evidence weights and thresholds in
sabha_asr.role_evidence; nothing is estimated here. A recording whose automatic decision was not kept (processed
before 2026-11-04) is listed with "automatic": null.

Reads each tenant's recordings through the tenant-scoped repository (golden rule 1) and the artefacts bucket.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import Recording, Tenant
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.settings import load_settings
from sabha_core.storage import artefact_prefix

EVAL_DIR = Path(__file__).resolve().parent


def _staff(roles: dict[str, Any], others: set[str]) -> str | None:
    """The one speaker whose role is not an other-side role, from roles@v1 records or plain {label: role}."""
    staff = [label for label, role in roles.items() if (role["role"] if isinstance(role, dict) else role) not in others]
    return staff[0] if len(staff) == 1 else None


def corrections(
    db: Database[dict[str, Any]], read: Any, *, conversation_type: str | None = None, version: str = "v1"
) -> Iterator[dict[str, Any]]:
    """One row per recording with reviewer-confirmed roles. `read(key)` returns an artefact's bytes, or raises
    FileNotFoundError."""
    for tenant in SyncSystemRepo(db, "tenants", Tenant).find({}, sort=[("_id", 1)]):
        query: dict[str, Any] = {"confirmed_roles": {"$ne": None}}
        if conversation_type is not None:
            query["type"] = conversation_type
        for recording in SyncTenantRepo(db, "recordings", tenant.id, Recording).find(query, sort=[("_id", 1)]):
            confirmed = recording.confirmed_roles or {}
            others = {"students", "caller", "customer", "visitor"}
            prefix = artefact_prefix(tenant.id, recording.id, "transcribe", version)
            try:
                auto = json.loads(read(prefix + "roles_auto@v1.json"))
            except FileNotFoundError:
                auto = None
            try:
                evidence = json.loads(read(prefix + "role_evidence@v1.json"))
            except FileNotFoundError:
                evidence = None
            auto_staff = _staff(auto, others) if auto else None
            reviewer_staff = _staff(confirmed, others)
            yield {
                "tenant_id": tenant.id,
                "recording_id": recording.id,
                "type": recording.type.value,
                "automatic": None if auto is None else {"staff": auto_staff,
                                                         "methods": sorted({r["method"] for r in auto.values()})},
                "reviewer": {"staff": reviewer_staff},
                "agree": None if auto is None else auto_staff == reviewer_staff,
                "evidence": evidence,
            }  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", help="only this conversation type, e.g. support")
    parser.add_argument("--out", type=Path, help="JSON Lines file (default eval/reports/role-corrections-<date>.jsonl)")
    args = parser.parse_args(argv)
    from sabha_workers.tasks import s3_client  # the worker's S3 client: same settings and bucket

    settings = load_settings()
    s3 = s3_client(settings)

    def read(key: str) -> bytes:
        try:
            body: bytes = s3.get_object(Bucket=settings.s3_bucket_artefacts, Key=key)["Body"].read()
        except s3.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        return body

    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        rows = list(corrections(client[settings.mongo_db], read, conversation_type=args.type,
                                version=settings.artefact_version_transcribe))  # fmt: skip
    finally:
        client.close()
    out = args.out or EVAL_DIR / "reports" / f"role-corrections-{datetime.now(UTC).date().isoformat()}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    judged = [row for row in rows if row["agree"] is not None]
    agreed = sum(1 for row in judged if row["agree"])
    print(f"{len(rows)} corrected recordings; automatic decision kept for {len(judged)}, of which {agreed} agreed "
          f"with the reviewer. Written to {out}", file=sys.stderr)  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
