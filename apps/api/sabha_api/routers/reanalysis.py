"""Re-analysis (sabha_api.services.reanalysis, plan task P2.8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import reanalysis as service
from sabha_core.models import (
    Analysis,
    AuditEntry,
    Dispute,
    IdempotencyRecord,
    OutboxEvent,
    Person,
    Recording,
    Transcript,
)  # fmt: skip
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["reanalysis"])

Caller = Annotated[Principal, Depends(current_principal)]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Transcripts = Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))]
Disputes = Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))]
Outbox = Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]
Key = Annotated[str | None, Header(alias=HEADER)]


@router.post("/v1/recordings/{recording_id}/reanalyze", response_model=service.ReanalyzeOut)
async def reanalyze(
    recording_id: str, body: service.ReanalyzeIn, request: Request, principal: Caller, recordings: Recordings,
    people: People, transcripts: Transcripts, disputes: Disputes, outbox: Outbox, entries: Entries, records: Records,
    txn: Txn, idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Score a finished recording again from its transcript (owners and admins). Earlier versions are kept."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.reanalyze(principal, recording_id, body, request,
                                      rubrics_dir=request.app.state.settings.rubrics_dir, recordings=recordings,
                                      people=people, transcripts=transcripts, disputes=disputes, outbox=outbox,
                                      entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    route = service.ROUTE.replace("{recording_id}", recording_id)
    return await idempotent(records, key=idempotency_key, route=route, body=body, handler=handler)


@router.post("/v1/reanalysis", response_model=service.BulkOut)
async def reanalyze_many(
    body: service.BulkIn, request: Request, principal: Caller, found: Annotated[Directory, Depends(directory)],
    recordings: Recordings, analyses: Analyses, transcripts: Transcripts, disputes: Disputes, outbox: Outbox,
    entries: Entries, records: Records, txn: Txn, idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Re-analyse the finished recordings of a type scored with another rubric: count first (dry_run), then at most
    100 per request (owners and admins)."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.reanalyze_many(principal, body, request, tenant=await found.tenant(principal.tenant_id),
                                           rubrics_dir=request.app.state.settings.rubrics_dir, recordings=recordings,
                                           analyses=analyses, transcripts=transcripts, disputes=disputes,
                                           outbox=outbox, entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.BULK_ROUTE, body=body, handler=handler)
