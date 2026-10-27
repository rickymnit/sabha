"""Change a tenant's plan or monthly audio-hour allowance (until the admin pages, P7.8).

Usage (from the repo root):

    uv run python scripts/admin/set_plan.py --tenant <tenant id> --plan starter --audio-hours 100
    uv run python scripts/admin/set_plan.py --tenant <tenant id> --no-audio-hours   # remove the allowance

Plans and allowances are agreed with the customer; a tenant's owner cannot change them (OwnTenantRepo). Prints the
tenant's plan and allowance after the change.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import Tenant
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo
from sabha_core.settings import load_settings

KEEP: Any = object()


def set_plan(db: Database[dict[str, Any]], tenant_id: str, *, plan: Plan | None = None,
             audio_hours: Any = KEEP) -> Tenant:  # fmt: skip  # float, None (remove) or KEEP
    """The tenant after the change. Raises LookupError for an unknown tenant, ValueError for a bad allowance."""
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    tenant = tenants.find_one({"_id": tenant_id})
    if tenant is None:
        raise LookupError(f"no tenant {tenant_id!r}")
    changes: dict[str, Any] = {}
    if plan is not None:
        changes["plan"] = plan
    if audio_hours is not KEEP:
        changes["audio_hours_allowance"] = audio_hours
    if not changes:
        return tenant
    changed = Tenant.model_validate({**tenant.model_dump(), **changes})  # the model's rules (allowance > 0)
    tenants.update_one({"_id": tenant_id}, {"$set": {k: getattr(changed, k) for k in changes}})
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--plan", choices=[p.value for p in Plan])
    hours = parser.add_mutually_exclusive_group()
    hours.add_argument("--audio-hours", type=float)
    hours.add_argument("--no-audio-hours", action="store_true")
    args = parser.parse_args(argv)
    audio_hours: Any = None if args.no_audio_hours else KEEP if args.audio_hours is None else args.audio_hours

    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        tenant = set_plan(client[settings.mongo_db], args.tenant, plan=Plan(args.plan) if args.plan else None,
                          audio_hours=audio_hours)  # fmt: skip
    except (LookupError, ValueError) as error:
        print(f"not changed: {error}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print(f"{tenant.id}: plan {tenant.plan}, audio hours {tenant.audio_hours_allowance or 'not set'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
