"""Reading the audit log (plan task P1.8): GET /v1/audit, for owners and admins.

Entries are append-only (sabha_core.repo.APPEND_ONLY) and written by sabha_api.audit.audit. This lists them newest
first with cursor pagination on (at, _id), and filters on action, actor, target and a time range. Each entry names
its actor (from users; None once the user is gone) and labels its target where there is something to show: a
recording's title, a dispute's recording title, an invited person's name.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from sabha_api.auth import Role
from sabha_api.errors import BadRequestError
from sabha_api.services.results import recording_title
from sabha_core.models import AuditEntry, Dispute, Person, Recording, Unit, User
from sabha_core.repo import TenantRepo

ALLOWED = (Role.OWNER, Role.ADMIN)
MAX_LIMIT = 200


class ActorOut(BaseModel):
    id: str
    name: str | None  # None once the user no longer exists
    role: str


class TargetOut(BaseModel):
    type: str
    id: str
    label: str | None


class EntryOut(BaseModel):
    id: str
    at: datetime
    action: str
    actor: ActorOut
    target: TargetOut
    meta: dict[str, Any]


class AuditPage(BaseModel):
    items: list[EntryOut]
    next_cursor: str | None


def _encode(at: datetime, entry_id: str) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{entry_id}".encode()).decode().rstrip("=")


def _after(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, entry_id = raw.split("|", 1)
        at = datetime.fromisoformat(stamp)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadRequestError("The cursor is not valid; start again without it.") from exc
    return {"$or": [{"at": {"$lt": at}}, {"at": at, "_id": {"$lt": entry_id}}]}


async def list_entries(
    *,
    entries: TenantRepo[AuditEntry],
    users: TenantRepo[User],
    recordings: TenantRepo[Recording],
    disputes: TenantRepo[Dispute],
    cursor: str | None,
    limit: int,
    people: TenantRepo[Person] | None = None,
    units: TenantRepo[Unit] | None = None,
    action: str | None = None,
    actor_user_id: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> AuditPage:
    conditions: list[dict[str, Any]] = [_after(cursor)]
    if action:
        conditions.append({"action": action})
    if actor_user_id:
        conditions.append({"actor_user_id": actor_user_id})
    if target_id:
        conditions.append({"target_id": target_id})
    if since or until:
        conditions.append({"at": {**({"$gte": since} if since else {}), **({"$lt": until} if until else {})}})
    kept = [c for c in conditions if c]
    found = await entries.find({"$and": kept} if kept else {}, sort=[("at", -1), ("_id", -1)], limit=limit + 1)
    page, more = found[:limit], len(found) > limit
    names, labels = await _names(page, users), await _labels(page, users, recordings, disputes, people, units)
    return AuditPage(
        items=[
            EntryOut(
                id=e.id,
                at=e.at,
                action=e.action,
                actor=ActorOut(id=e.actor_user_id, name=names.get(e.actor_user_id), role=e.actor_role),
                target=TargetOut(type=e.target_type, id=e.target_id, label=labels.get((e.target_type, e.target_id))),
                meta=e.meta,
            )
            for e in page
        ],
        next_cursor=_encode(page[-1].at, page[-1].id) if more and page else None,
    )


async def _names(page: list[AuditEntry], users: TenantRepo[User]) -> dict[str, str]:
    ids = list({e.actor_user_id for e in page})
    return {u.id: u.name for u in await users.find({"_id": {"$in": ids}})} if ids else {}


async def _labels(
    page: list[AuditEntry],
    users: TenantRepo[User],
    recordings: TenantRepo[Recording],
    disputes: TenantRepo[Dispute],
    people: TenantRepo[Person] | None = None,
    units: TenantRepo[Unit] | None = None,
) -> dict[tuple[str, str], str]:
    """(target type, id) -> what to show for it."""

    def of(kind: str) -> list[str]:
        return list({e.target_id for e in page if e.target_type == kind})

    labels: dict[tuple[str, str], str] = {}
    if ids := of("user"):
        labels |= {("user", u.id): u.name for u in await users.find({"_id": {"$in": ids}})}
    found_disputes = await disputes.find({"_id": {"$in": ids}}) if (ids := of("dispute")) else []
    recording_ids = list({*of("recording"), *(d.recording_id for d in found_disputes)})
    titles = (
        {r.id: recording_title(r.file_name, r.id) for r in await recordings.find({"_id": {"$in": recording_ids}})}
        if recording_ids
        else {}
    )
    labels |= {("recording", rid): title for rid, title in titles.items()}
    labels |= {("dispute", d.id): titles[d.recording_id] for d in found_disputes if d.recording_id in titles}
    if people is not None and (ids := of("person")):
        labels |= {("person", p.id): p.name for p in await people.find({"_id": {"$in": ids}})}
    if units is not None and (ids := of("unit")):
        labels |= {("unit", u.id): u.name for u in await units.find({"_id": {"$in": ids}})}
    return labels
