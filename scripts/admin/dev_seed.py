"""Seed a demo school for the local dev sign-in (APP_ENV=local only; sabha_api.auth.dev_idp).

Usage (from the repo root, with `make dev` running and in .env: APP_ENV=local, DEV_LOGIN=true,
OIDC_ISSUER=http://localhost:8000/dev-idp, OIDC_AUDIENCE=sabha-local, OIDC_CLIENT_ID=sabha-web):

    uv run python scripts/admin/dev_seed.py

Creates, once (running it again changes nothing), the tenant "Demo School" (school profile, pilot plan) with two
units and one active user per role, each linked to the dev issuer as subject "dev-<name>", so the web app's
"Sign in as..." list shows them. The two staff members are also people (Asha in Class 6, Ravi in Class 7), so
recordings can be uploaded for them. Everything is made up; never point this at a real database.
"""

from __future__ import annotations

import sys
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Person, Role, Tenant, Unit, User
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.settings import load_settings

TENANT_ID = "demo-school"
UNITS = {"unit-6": "Class 6", "unit-7": "Class 7"}
USERS = [  # (subject suffix, name, job title, role, units, person id)
    ("owner", "Priya Sharma", "Principal", Role.OWNER, [], None),
    ("admin", "Neha Joshi", "School office", Role.ADMIN, [], None),
    ("manager", "Meena Iyer", "Coordinator, Class 6", Role.MANAGER, ["unit-6"], None),
    ("reviewer", "Rahul Verma", "Senior teacher, Class 6", Role.REVIEWER, ["unit-6"], None),
    ("asha", "Asha Rao", "Teacher, Class 6", Role.STAFF, ["unit-6"], "p-asha"),
    ("ravi", "Ravi Kumar", "Teacher, Class 7", Role.STAFF, ["unit-7"], "p-ravi"),
]


def seed(db: Database[dict[str, Any]], issuer: str) -> int:
    """Create what is missing; return how many documents were written."""
    ensure_indexes(db)
    written = 0
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    if tenants.find_one({"_id": TENANT_ID}) is None:
        tenants.insert_one(Tenant.from_profile("school", name="Demo School", plan=Plan.PILOT, id=TENANT_ID))
        written += 1
    units = SyncTenantRepo(db, "units", TENANT_ID, Unit)
    people = SyncTenantRepo(db, "people", TENANT_ID, Person)
    users = SyncTenantRepo(db, "users", TENANT_ID, User)
    identities = SyncSystemRepo(db, "identities", IdentityLink)
    for unit_id, name in UNITS.items():
        if units.find_one({"_id": unit_id}) is None:
            units.insert_one(Unit(id=unit_id, name=name))
            written += 1
    for suffix, name, title, role, unit_ids, person_id in USERS:
        user_id, email, subject = f"u-dev-{suffix}", f"{suffix}@demo-school.example", f"dev-{suffix}"
        existing = users.find_one({"_id": user_id})
        if existing is None:
            users.insert_one(User(id=user_id, email=email, name=name, title=title, role=role, unit_ids=unit_ids,
                                  status="active"))  # fmt: skip
            written += 1
        elif (existing.name, existing.title) != (name, title):  # older seeds put the title in the name
            written += users.update_one({"_id": user_id}, {"$set": {"name": name, "title": title}})
        if identities.find_one({"issuer": issuer, "subject": subject}) is None:
            identities.insert_one(IdentityLink(tenant_id=TENANT_ID, issuer=issuer, subject=subject, email=email,
                                               user_id=user_id))  # fmt: skip
            written += 1
        if person_id and people.find_one({"_id": person_id}) is None:
            people.insert_one(Person(id=person_id, name=name, unit_id=unit_ids[0], user_id=user_id))
            written += 1
    return written


def main() -> int:
    settings = load_settings()
    if settings.app_env != "local" or not settings.dev_login:
        print("dev_seed runs only with APP_ENV=local and DEV_LOGIN=true", file=sys.stderr)
        return 2
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value())
    written = seed(client[settings.mongo_db], settings.oidc_issuer)
    print(f"Demo School ready ({written} documents written). Sign in at the web app with any of: "
          + ", ".join(f"dev-{u[0]}" for u in USERS))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
