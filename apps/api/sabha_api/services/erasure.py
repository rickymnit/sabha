"""Erasure on request (plan task P7.3, DPDP; owner's decision 2026-10-27: owners only, one recording or one person;
a whole tenant is erased by Sabha with a script).

POST /v1/erasure {scope, id, reason, confirm}:
- Without confirm: counts what would go (recordings, documents per collection, stored files). Nothing changes.
- With confirm: deletes every stored file under each recording's prefix (both buckets) first, then in one
  transaction every document about those recordings (recordings, transcripts, analyses, scores, disputes,
  stage_runs, dlq, llm_calls and their outbox events) and, for a person, the person, their user account and login
  links. Files first, so a failure part-way leaves documents that a second request finishes erasing.
- One audit entry, data.erase, keeps the minimal record that it happened: who, when, why, and the counts. No names
  or content (docs/legal/drafts/staff-consent-and-notice.md).

Kept on purpose: the append-only audit log, usage records (a recording id and its length, for invoicing) and email
delivery receipts; none holds recording content.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import Request
from pydantic import BaseModel, StringConstraints

from sabha_api.audit import audit
from sabha_api.auth import Principal, Role
from sabha_api.deps import Transactions
from sabha_api.errors import ForbiddenError, NotFoundError
from sabha_core.models import AuditEntry, Person, Recording
from sabha_core.repo import TenantRepo
from sabha_core.settings import Settings
from sabha_core.storage import delete_objects, recording_prefix

ROUTE = "POST /v1/erasure"
ALLOWED = frozenset({Role.OWNER})
# Collections holding documents about one recording, and the field that names it.
BY_RECORDING = {
    "transcripts": "recording_id", "analyses": "recording_id", "scores": "recording_id", "disputes": "recording_id",
    "stage_runs": "recording_id", "dlq": "recording_id", "llm_calls": "recording_id", "outbox": "payload.recording_id",
}  # fmt: skip

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ErasureIn(BaseModel):
    scope: Literal["recording", "person"]
    id: str
    reason: Reason
    confirm: bool = False


class ErasureOut(BaseModel):
    scope: str
    id: str
    erased: bool
    recordings: int
    documents: dict[str, int]
    files: int


Repos = dict[str, TenantRepo[Any]]  # collection name -> repository, from the router


async def erase(
    principal: Principal, body: ErasureIn, request: Request, *, settings: Settings, s3: Any, repos: Repos,
    entries: TenantRepo[AuditEntry], transactions: Transactions,
) -> ErasureOut:  # fmt: skip
    if principal.role not in ALLOWED:
        raise ForbiddenError("Only the owner can erase data.")
    recordings: TenantRepo[Recording] = repos["recordings"]
    people: TenantRepo[Person] = repos["people"]
    person = None
    if body.scope == "person":
        person = await people.find_one({"_id": body.id})
        if person is None:
            raise NotFoundError("This person does not exist in your organisation.")
        ids = [r.id for r in await recordings.find({"person_id": person.id})]
    else:
        if await recordings.find_one({"_id": body.id}) is None:
            raise NotFoundError("This recording does not exist in your organisation.")
        ids = [body.id]

    documents = {"recordings": len(ids)}
    for collection, field in BY_RECORDING.items():
        found = repos[collection]
        documents[collection] = await found.count({field: {"$in": ids}}) if ids else 0
    if person is not None:
        documents["people"] = 1
        documents["users"] = 1 if person.user_id else 0
        links = repos["identities"]
        documents["identities"] = await links.count({"user_id": person.user_id}) if person.user_id else 0
    files = await _files(s3, settings, principal.tenant_id, ids, dry_run=True)
    out = ErasureOut(scope=body.scope, id=body.id, erased=False, recordings=len(ids), documents=documents, files=files)
    if not body.confirm:
        return out

    await _files(s3, settings, principal.tenant_id, ids, dry_run=False)
    async with transactions.run() as session:
        if ids:
            for collection, field in BY_RECORDING.items():
                target = repos[collection]
                await target.delete_many({field: {"$in": ids}}, session=session)
            await recordings.delete_many({"_id": {"$in": ids}}, session=session)
        if person is not None:
            await people.delete_many({"_id": person.id}, session=session)
            if person.user_id:
                users, identities = repos["users"], repos["identities"]
                await users.delete_many({"_id": person.user_id}, session=session)
                await identities.delete_many({"user_id": person.user_id}, session=session)
        await audit(entries, principal, request, action="data.erase", target_type=body.scope, target_id=body.id,
                    meta={"reason": body.reason, "recordings": len(ids), "documents": documents, "files": files},
                    session=session)  # fmt: skip
    return out.model_copy(update={"erased": True})


async def _files(s3: Any, settings: Settings, tenant_id: str, ids: list[str], *, dry_run: bool) -> int:
    """Stored files under each recording's prefix, in both buckets (boto3 is blocking: run it off the loop)."""

    def run() -> int:
        return sum(
            delete_objects(s3, bucket, recording_prefix(tenant_id, rid), dry_run=dry_run)
            for rid in ids
            for bucket in (settings.s3_bucket_audio, settings.s3_bucket_artefacts)
        )

    return await asyncio.to_thread(run)
