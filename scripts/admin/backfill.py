"""Fill in fields added after recordings were processed (UI v2): speaker strips. Use --dry-run first.

uv run python scripts/admin/backfill.py --dry-run
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from pymongo import MongoClient

from sabha_core.settings import load_settings
from sabha_workers.backfill import backfill_strips
from sabha_workers.tasks import s3_client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only count what would be filled in")
    args = parser.parse_args(argv)
    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        done = backfill_strips(client[settings.mongo_db], s3_client(settings),
                               artefacts_bucket=settings.s3_bucket_artefacts, dry_run=args.dry_run)  # fmt: skip
    finally:
        client.close()
    verb = "would fill" if args.dry_run else "filled"
    for d in done:
        print(f"{d.tenant_id}: {verb} {d.strips} speaker strips; {d.missing_files} transcript files missing")
    if not done:
        print("nothing to fill in")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
