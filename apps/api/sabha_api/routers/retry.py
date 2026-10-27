"""Retrying or closing a failed recording, and how it was processed (sabha_api.services.retry and .processing, P7.8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import processing as processing_service
from sabha_api.services import retry as service
from sabha_core.models import (
    AuditEntry,
    DeadLetter,
    IdempotencyRecord,
    LlmCall,
    OutboxEvent,
    Person,
    Recording,
    StageRun,
)
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["recordings"])

Caller = Annotated[Principal, Depends(current_principal)]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Letters = Annotated[TenantRepo[DeadLetter], Depends(tenant_repo("dlq", DeadLetter))]
Outbox = Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]
Key = Annotated[str | None, Header(alias=HEADER)]


@router.post("/v1/recordings/{recording_id}/retry", response_model=service.RetryOut)
async def retry_recording(
    recording_id: str, body: service.ReasonIn, request: Request, principal: Caller, recordings: Recordings,
    people: People, dlq: Letters, outbox: Outbox, entries: Entries, records: Records, txn: Txn,
    idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Run a failed recording's failed stage again (owners and admins). Earlier stages are not repeated."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.retry(principal, recording_id, body, request, recordings=recordings, people=people,
                                  dlq=dlq, outbox=outbox, entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    route = service.RETRY_ROUTE.replace("{recording_id}", recording_id)
    return await idempotent(records, key=idempotency_key, route=route, body=body, handler=handler)


@router.post("/v1/recordings/{recording_id}/abandon", response_model=service.RetryOut)
async def abandon_recording(
    recording_id: str, body: service.ReasonIn, request: Request, principal: Caller, recordings: Recordings,
    people: People, dlq: Letters, entries: Entries, records: Records, txn: Txn, idempotency_key: Key = None,
) -> JSONResponse:  # fmt: skip
    """Close a failed recording for good, with the reason (owners and admins). It can no longer be retried."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.abandon(principal, recording_id, body, request, recordings=recordings, people=people,
                                    dlq=dlq, entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    route = service.ABANDON_ROUTE.replace("{recording_id}", recording_id)
    return await idempotent(records, key=idempotency_key, route=route, body=body, handler=handler)


@router.get("/v1/recordings/{recording_id}/processing", response_model=processing_service.ProcessingOut)
async def recording_processing(
    recording_id: str, principal: Caller, recordings: Recordings, people: People, dlq: Letters,
    runs: Annotated[TenantRepo[StageRun], Depends(tenant_repo("stage_runs", StageRun))],
    llm_calls: Annotated[TenantRepo[LlmCall], Depends(tenant_repo("llm_calls", LlmCall))],
) -> processing_service.ProcessingOut:  # fmt: skip
    """Each stage's runs, the latest failure and whether it can be retried, and the recorded AI cost (owners and
    admins)."""
    return await processing_service.processing(principal, recording_id, recordings=recordings, people=people,
                                               runs=runs, dlq=dlq, llm_calls=llm_calls)  # fmt: skip
