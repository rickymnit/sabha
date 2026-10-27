"""Create a tenant from an organisation profile and invite its first owner (until the tenant admin API, P7.8).

Usage (from the repo root):

    uv run python scripts/admin/create_tenant.py --name "Green Valley School" --profile school --plan pilot \
        --owner-email principal@example.com --owner-name "Asha Rao" --audio-hours 100

--audio-hours is the monthly allowance agreed with the customer; leave it out until there is one (the sidebar then
shows hours used without a limit). scripts/admin/set_plan.py changes it later.

The owner then signs in with that email (verified by the identity provider) and becomes active (ADR 0002). Indexes
are created first, so this also works on an empty database. Prints the new tenant id.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Role, Tenant, User
from sabha_core.profiles import ProfileName
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.settings import load_settings


def create_tenant(
    db: Database[dict[str, Any]],
    *,
    name: str,
    profile: ProfileName | str,
    plan: Plan,
    owner_email: str,
    owner_name: str,
    issuer: str,
    audio_hours: float | None = None,
) -> tuple[Tenant, User]:
    """The tenant, its owner (status "invited") and the owner's pending invite, written in one transaction."""
    ensure_indexes(db)
    tenant = Tenant.from_profile(profile, name=name, plan=plan, audio_hours_allowance=audio_hours)
    owner = User(email=owner_email, name=owner_name, role=Role.OWNER, status="invited")
    with db.client.start_session() as session, session.start_transaction():
        SyncSystemRepo(db, "tenants", Tenant).insert_one(tenant, session=session)
        owner = SyncTenantRepo(db, "users", tenant.id, User).insert_one(owner, session=session)
        invite = IdentityLink(issuer=issuer, email=owner.email, user_id=owner.id)
        SyncTenantRepo(db, "identities", tenant.id, IdentityLink).insert_one(invite, session=session)
    return tenant, owner


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True)
    parser.add_argument("--profile", choices=[p.value for p in ProfileName], default=ProfileName.SCHOOL.value)
    parser.add_argument("--plan", choices=[p.value for p in Plan], default=Plan.PILOT.value)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-name", required=True)
    parser.add_argument("--audio-hours", type=float, default=None, help="monthly audio-hour allowance, if agreed")
    args = parser.parse_args(argv)

    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        tenant, owner = create_tenant(
            client[settings.mongo_db],
            name=args.name,
            profile=args.profile,
            plan=Plan(args.plan),
            owner_email=args.owner_email,
            owner_name=args.owner_name,
            issuer=settings.oidc_issuer,
            audio_hours=args.audio_hours,
        )
    finally:
        client.close()
    print(f"tenant {tenant.id} created; {owner.email} invited as owner", file=sys.stderr)
    print(tenant.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
