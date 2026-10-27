"""Restore drill (P7.3): load a backup into a scratch database and check it. Run it monthly and after any change to
the backup job; record the result in docs/runbook.md.

    uv run python scripts/admin/restore_drill.py            # the latest backup, scratch database dropped after
    uv run python scripts/admin/restore_drill.py --day 2026-10-27 --keep
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from pymongo import MongoClient

from sabha_core.backup import RESTORE_PREFIX, latest_backup, restore_drill
from sabha_core.settings import load_settings
from sabha_workers.tasks import s3_client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--day", help="YYYY-MM-DD; the latest backup if left out")
    parser.add_argument("--keep", action="store_true", help="keep the scratch database for inspection")
    args = parser.parse_args(argv)
    settings = load_settings()
    s3 = s3_client(settings)
    day = args.day or latest_backup(s3, settings.s3_bucket_backups)
    target = f"{RESTORE_PREFIX}{day.replace('-', '')}"
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        report = restore_drill(client, s3, settings.s3_bucket_backups, day=day, target=target)
        if not args.keep:
            client.drop_database(target)
    finally:
        client.close()
    for name, count in sorted(report.collections.items()):
        print(f"{name:20} {count:>8} documents")
    for problem in report.problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    print(f"restore drill of {day}: {'PASSED' if report.passed else 'FAILED'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
