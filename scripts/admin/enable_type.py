"""Switch a conversation type on for every existing tenant of a profile (a new type reaching existing customers).

Usage (from the repo root):

    uv run python scripts/admin/enable_type.py --type support --profile company --dry-run
    uv run python scripts/admin/enable_type.py --type support --profile company

New tenants get a profile's types when they are created (Tenant.from_profile); this brings tenants created before a
type existed up to date. Support was added for companies on 2026-11-04 and the owner chose to switch it on for every
existing company. A tenant is left as it is, and listed, when the type is already on, when its profile has no rubric
for the type, or when one more type would go past its plan's limit (sabha_core.quota.MAX_TYPES); an admin can then
switch another type off and this one on in Settings. Each change and its audit entry (settings.update, by "system",
as the Settings page writes it) are written in one transaction. Running it again changes nothing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import AuditEntry, Tenant
from sabha_core.profiles import ConversationType, ProfileName, get_profile
from sabha_core.quota import MAX_TYPES
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.settings import load_settings


@dataclass
class Outcome:
    enabled: list[str] = field(default_factory=list)
    already_on: list[str] = field(default_factory=list)
    over_plan_limit: list[str] = field(default_factory=list)


def enable_type(
    client: MongoClient[dict[str, Any]], db: Database[dict[str, Any]], conversation_type: ConversationType,
    profile: ProfileName, *, dry_run: bool = False,
) -> Outcome:  # fmt: skip
    """Switch `conversation_type` on for every tenant of `profile` (module docstring). Raises ValueError when the
    profile has no rubric for the type, so no tenant could use it."""
    if get_profile(profile).default_rubrics.get(conversation_type) is None:
        raise ValueError(f"the {profile} profile has no rubric for {conversation_type}")
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    outcome = Outcome()
    for tenant in tenants.find({"profile": profile.value}, sort=[("_id", 1)]):
        if conversation_type in tenant.enabled_types:
            outcome.already_on.append(tenant.id)
            continue
        types = [t for t in ConversationType if t in tenant.enabled_types or t is conversation_type]  # setup order
        if len(types) > MAX_TYPES[tenant.plan]:
            outcome.over_plan_limit.append(tenant.id)
            continue
        outcome.enabled.append(tenant.id)
        if dry_run:
            continue
        before, after = [t.value for t in tenant.enabled_types], [t.value for t in types]
        with client.start_session() as session, session.start_transaction():
            tenants.update_one({"_id": tenant.id, "enabled_types": before}, {"$set": {"enabled_types": after}},
                               session=session)  # fmt: skip
            SyncTenantRepo(db, "audit_log", tenant.id, AuditEntry).insert_one(
                AuditEntry(
                    actor_user_id="system", actor_role="system", action="settings.update", target_type="tenant",
                    target_id=tenant.id,
                    meta={"before": {"enabled_types": before}, "after": {"enabled_types": after},
                          "reason": f"{conversation_type.value} added to the {profile.value} profile"},
                ),
                session=session,
            )  # fmt: skip
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--type", required=True, choices=[t.value for t in ConversationType])
    parser.add_argument("--profile", required=True, choices=[p.value for p in ProfileName])
    parser.add_argument("--dry-run", action="store_true", help="list what would change and change nothing")
    args = parser.parse_args(argv)

    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        outcome = enable_type(client, client[settings.mongo_db], ConversationType(args.type),
                              ProfileName(args.profile), dry_run=args.dry_run)  # fmt: skip
    finally:
        client.close()
    verb = "would switch on" if args.dry_run else "switched on"
    print(f"{args.type} {verb} for {len(outcome.enabled)}: {', '.join(outcome.enabled) or '-'}")
    print(f"already on for {len(outcome.already_on)}: {', '.join(outcome.already_on) or '-'}")
    if outcome.over_plan_limit:
        print(f"NOT switched on, plan limit reached, for {len(outcome.over_plan_limit)}: "
              f"{', '.join(outcome.over_plan_limit)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
