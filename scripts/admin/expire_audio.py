"""Run audio retention by hand (P7.3); the worker's beat runs it nightly. Use --dry-run first to see what goes.

uv run python scripts/admin/expire_audio.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from pymongo import MongoClient

from sabha_core.models import utc_now
from sabha_core.settings import load_settings
from sabha_workers.retention import expire_audio
from sabha_workers.tasks import s3_client


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only count what would be deleted")
    args = parser.parse_args(argv)
    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        buckets = {"audio_bucket": settings.s3_bucket_audio, "artefacts_bucket": settings.s3_bucket_artefacts}
        done = expire_audio(client[settings.mongo_db], s3_client(settings), now=utc_now(), dry_run=args.dry_run,
                            **buckets)  # fmt: skip
    finally:
        client.close()
    verb = "would delete" if args.dry_run else "deleted"
    for d in done:
        print(f"{d.tenant_id}: {verb} audio of {d.recordings} recordings ({d.objects} files)")
    if not done:
        print("nothing has expired", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
