"""Seed a demo school for the local dev sign-in (APP_ENV=local only; sabha_api.auth.dev_idp).

Usage (from the repo root, with `make dev` running and in .env: APP_ENV=local, DEV_LOGIN=true,
OIDC_ISSUER=http://localhost:8000/dev-idp, OIDC_AUDIENCE=sabha-local, OIDC_CLIENT_ID=sabha-web):

    uv run python scripts/admin/dev_seed.py

Creates, once (running it again changes nothing), the tenant "Demo School" (school profile, pilot plan) with two
units and one active user per role, each linked to the dev issuer as subject "dev-<name>", so the web app's
"Sign in as..." list shows them. The two staff members are also people (Asha in Class 6, Ravi in Class 7), so
recordings can be uploaded for them. Everything is made up; never point this at a real database.

It also seeds "Brightpath Software" (tenant demo-company, company profile): a fictional software company whose sales
reps record in-person sales meetings, team meetings, and walk-in visitors at its front desk (Pooja, the
receptionist).

And "E2E School" (tenant e2e-school) for the browser tests (apps/web/e2e): an owner and a teacher whose
uploads stay out of the demo school. The dev sign-in page does not list it (dev_idp.HIDDEN_TENANT_PREFIX).
"""

from __future__ import annotations

import sys
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.indexes import ensure_indexes
from sabha_core.models import IdentityLink, Person, Role, Tenant, Unit, User
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_core.repo import SyncSystemRepo, SyncTenantRepo
from sabha_core.settings import load_settings

TENANT_ID = "demo-school"
TENANT_NAME = "Demo School"
UNITS = {"unit-6": "Class 6", "unit-7": "Class 7"}
USERS = [  # (subject suffix, name, job title, role, units, person id)
    ("owner", "Priya Sharma", "Principal", Role.OWNER, [], None),
    ("admin", "Neha Joshi", "School office", Role.ADMIN, [], None),
    ("manager", "Meena Iyer", "Coordinator, Class 6", Role.MANAGER, ["unit-6"], None),
    ("reviewer", "Rahul Verma", "Senior teacher, Class 6", Role.REVIEWER, ["unit-6"], None),
    ("asha", "Asha Rao", "Teacher, Class 6", Role.STAFF, ["unit-6"], "p-asha"),
    ("ravi", "Ravi Kumar", "Teacher, Class 7", Role.STAFF, ["unit-7"], "p-ravi"),
]
COMPANY_TENANT_ID, COMPANY_NAME = "demo-company", "Brightpath Software"
COMPANY_UNITS = {"team-north": "North team", "team-south": "South team", "front-desk": "Front desk"}
COMPANY_USERS = [  # (subject suffix, name, job title, role, units, person id)
    ("kabir", "Kabir Mehta", "Founder and CEO", Role.OWNER, [], None),
    ("ananya", "Ananya Rao", "Sales head, North", Role.MANAGER, ["team-north"], None),
    ("rohit", "Rohit Sharma", "Sales rep, North", Role.STAFF, ["team-north"], "p-rohit"),
    ("neha", "Neha Gupta", "Sales rep, South", Role.STAFF, ["team-south"], "p-neha"),
    ("pooja", "Pooja Nair", "Receptionist", Role.STAFF, ["front-desk"], "p-pooja"),
]
COMPANY_TYPES = [ConversationType.RECEPTION, ConversationType.SALES, ConversationType.MEETING]
# How the speech recogniser writes the name when it is said inside Hindi speech.
COMPANY_NAME_VARIANTS = ["Brightpath", "ब्राइट पाथ सॉफ्टवेयर", "ब्राइट पाथ", "ब्राइटपाथ"]
E2E_TENANT_ID, E2E_TENANT_NAME = "e2e-school", "E2E School"
E2E_UNITS = {"unit-e2e": "Test class"}
E2E_USERS = [
    ("e2e-owner", "Test Principal", "Principal", Role.OWNER, [], None),
    ("e2e-teacher", "Test Teacher", "Teacher, Test class", Role.STAFF, ["unit-e2e"], "p-e2e"),
]


def seed(db: Database[dict[str, Any]], issuer: str) -> int:
    """Create what is missing; return how many documents were written."""
    ensure_indexes(db)
    demo = [(f"dev-{u[0]}", f"u-dev-{u[0]}", f"{u[0]}@demo-school.example", *u[1:]) for u in USERS]
    e2e = [(u[0], f"u-{u[0]}", f"{u[0]}@e2e-school.example", *u[1:]) for u in E2E_USERS]
    company = [(f"dev-{u[0]}", f"u-dev-{u[0]}", f"{u[0]}@brightpath.example", *u[1:]) for u in COMPANY_USERS]
    return (
        _seed_tenant(db, issuer, TENANT_ID, TENANT_NAME, UNITS, demo)
        + _seed_tenant(
            db,
            issuer,
            COMPANY_TENANT_ID,
            COMPANY_NAME,
            COMPANY_UNITS,
            company,
            profile="company",
            enabled_types=COMPANY_TYPES,
            name_variants=COMPANY_NAME_VARIANTS,
        )
        + _seed_tenant(db, issuer, E2E_TENANT_ID, E2E_TENANT_NAME, E2E_UNITS, e2e)
    )


def _seed_tenant(
    db: Database[dict[str, Any]], issuer: str, tenant_id: str, tenant_name: str, unit_names: dict[str, str],
    people_rows: list[tuple[str, str, str, str, str, Role, list[str], str | None]], *, profile: str = "school",
    enabled_types: list[ConversationType] | None = None, name_variants: list[str] | None = None,
) -> int:  # fmt: skip
    """One tenant: its units, and per row (subject, user id, email, name, title, role, units, person id)."""
    written = 0
    tenants = SyncSystemRepo(db, "tenants", Tenant)
    if tenants.find_one({"_id": tenant_id}) is None:
        types = {"enabled_types": enabled_types} if enabled_types is not None else {}
        tenants.insert_one(Tenant.from_profile(profile, name=tenant_name, plan=Plan.PILOT, id=tenant_id,
                                               name_variants=name_variants or [], **types))  # fmt: skip
        written += 1
    else:  # an earlier seed: bring the variants and conversation types up to date
        wanted = {
            **({"name_variants": name_variants} if name_variants else {}),
            **({"enabled_types": [t.value for t in enabled_types]} if enabled_types else {}),
        }
        if wanted and tenants.find_one({"_id": tenant_id, **wanted}) is None:
            tenants.update_one({"_id": tenant_id}, {"$set": wanted})
            written += 1
    units = SyncTenantRepo(db, "units", tenant_id, Unit)
    people = SyncTenantRepo(db, "people", tenant_id, Person)
    users = SyncTenantRepo(db, "users", tenant_id, User)
    identities = SyncSystemRepo(db, "identities", IdentityLink)
    for unit_id, name in unit_names.items():
        if units.find_one({"_id": unit_id}) is None:
            units.insert_one(Unit(id=unit_id, name=name))
            written += 1
    for subject, user_id, email, name, title, role, unit_ids, person_id in people_rows:
        existing = users.find_one({"_id": user_id})
        if existing is None:
            users.insert_one(User(id=user_id, email=email, name=name, title=title, role=role, unit_ids=unit_ids,
                                  status="active"))  # fmt: skip
            written += 1
        elif (existing.name, existing.title) != (name, title):  # older seeds put the title in the name
            written += users.update_one({"_id": user_id}, {"$set": {"name": name, "title": title}})
        if identities.find_one({"issuer": issuer, "subject": subject}) is None:
            identities.insert_one(IdentityLink(tenant_id=tenant_id, issuer=issuer, subject=subject, email=email,
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
    print(f"Demo School, Brightpath Software and E2E School ready ({written} documents written). Sign in at the web "
          "app as any of: " + ", ".join(f"dev-{u[0]}" for u in (*USERS, *COMPANY_USERS)))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
