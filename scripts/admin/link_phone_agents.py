"""Link every MyOperator agent to a person in Sabha, adding the people who are not there yet (ADR 0017).

Usage (from the repo root):

    uv run python scripts/admin/link_phone_agents.py --tenant demo-company --unit "Support team" --dry-run
    uv run python scripts/admin/link_phone_agents.py --tenant demo-company --unit "Support team"

Each agent who answered a call in `phone_calls` is matched by name (ignoring case and spaces) to a person of the
tenant. A person found is used as they are; otherwise one is added in the given unit. Agents with the same name (one
person on two extensions) go to the same person. The agent is then linked to the person (Person.phone_agent_ids,
moved from anyone else), and the person and unit are set on all the agent's calls, as the Phone calls page does when
someone links an agent. Each agent's changes and their audit entries (person.create, phone_agent.match, by
"system") are written in one transaction. Running it again changes nothing.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from sabha_core.models import AuditEntry, Person, PhoneCall, Unit
from sabha_core.repo import SyncTenantRepo
from sabha_core.settings import load_settings


@dataclass
class Outcome:
    added: list[str] = field(default_factory=list)  # people added
    linked: list[str] = field(default_factory=list)  # "agent (ext) -> person"
    already: list[str] = field(default_factory=list)  # agents linked as they should be


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()


def link_agents(client: MongoClient[dict[str, Any]], db: Database[dict[str, Any]], tenant_id: str, unit_name: str, *,
                dry_run: bool) -> Outcome:  # fmt: skip
    units = SyncTenantRepo(db, "units", tenant_id, Unit)
    unit = next((u for u in units.find({}) if _key(u.name) == _key(unit_name)), None)
    if unit is None:
        raise SystemExit(f"no unit named {unit_name!r} in {tenant_id}")
    people = SyncTenantRepo(db, "people", tenant_id, Person)
    calls = SyncTenantRepo(db, "phone_calls", tenant_id, PhoneCall)
    entries = SyncTenantRepo(db, "audit_log", tenant_id, AuditEntry)
    agents = calls.aggregate([
        {"$group": {"_id": {"$arrayElemAt": ["$agents.user_id", 0]},
                    "name": {"$last": {"$arrayElemAt": ["$agents.name", 0]}},
                    "extension": {"$last": {"$arrayElemAt": ["$agents.extension", 0]}}}},
        {"$sort": {"name": 1}},
    ])  # fmt: skip
    by_name = {_key(p.name): p for p in people.find({})}
    outcome = Outcome()
    for agent in agents:
        agent_id, name = str(agent["_id"] or ""), str(agent["name"] or "").strip()
        if not agent_id or not name:
            continue
        label = f"{name} (ext {agent.get('extension') or '?'})"
        person = by_name.get(_key(name))
        created = person is None
        if person is None:
            person = Person(name=name, unit_ids=[unit.id])
            by_name[_key(name)] = person
            outcome.added.append(name)
        elif agent_id in person.phone_agent_ids and not calls.count(
            {"agents.0.user_id": agent_id, "person_id": {"$ne": person.id}}
        ):
            outcome.already.append(label)
            continue
        outcome.linked.append(f"{label} -> {person.name}")
        if dry_run:
            continue
        with client.start_session() as session, session.start_transaction():
            if created:
                people.insert_one(person, session=session)
                entries.insert_one(AuditEntry(actor_user_id="system", actor_role="system", action="person.create",
                                              target_type="person", target_id=person.id,
                                              meta={"name": person.name, "unit_ids": person.unit_ids,
                                                    "from": "phone_agents"}), session=session)  # fmt: skip
            people.update_many({"phone_agent_ids": agent_id, "_id": {"$ne": person.id}},
                               {"$pull": {"phone_agent_ids": agent_id}}, session=session)  # fmt: skip
            people.update_one({"_id": person.id}, {"$addToSet": {"phone_agent_ids": agent_id}}, session=session)
            owner = {"$set": {"person_id": person.id, "unit_id": person.unit_id}}
            calls.update_many({"agents.0.user_id": agent_id}, owner, session=session)
            entries.insert_one(AuditEntry(actor_user_id="system", actor_role="system", action="phone_agent.match",
                                          target_type="person", target_id=person.id,
                                          meta={"agent_name": name, "extension": agent.get("extension")}),
                               session=session)  # fmt: skip
        person.phone_agent_ids.append(agent_id)
    return outcome


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", required=True, help="the workspace id, e.g. demo-company")
    parser.add_argument("--unit", required=True, help="the unit new people are added to, e.g. 'Support team'")
    parser.add_argument("--dry-run", action="store_true", help="list what would change and change nothing")
    args = parser.parse_args(argv)

    settings = load_settings()
    client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    try:
        outcome = link_agents(client, client[settings.mongo_db], args.tenant, args.unit, dry_run=args.dry_run)
    finally:
        client.close()
    verb = "would" if args.dry_run else "did"
    print(f"people added ({verb}): {', '.join(outcome.added) or '-'}")
    print(f"agents linked ({verb}):")
    for line in outcome.linked:
        print(f"  {line}")
    print(f"already linked: {', '.join(outcome.already) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
