"""Disputes (sabha_api.services.disputes, plan task P6.7)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import disputes as service
from sabha_core.models import (
    Analysis,
    AuditEntry,
    Dispute,
    IdempotencyRecord,
    OutboxEvent,
    Person,
    Recording,
    Score,
    Unit,
)  # fmt: skip
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["disputes"])

Caller = Annotated[Principal, Depends(current_principal)]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Units = Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))]
Scores = Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))]
Disputes = Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))]
Outbox = Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]
Txn = Annotated[Transactions, Depends(transactions)]


@router.post("/v1/analyses/{analysis_id}/disputes", status_code=201, response_model=service.DisputeOut)
async def raise_dispute(
    analysis_id: str, body: service.DisputeIn, request: Request, principal: Caller, analyses: Analyses,
    recordings: Recordings, people: People, scores: Scores, disputes: Disputes, entries: Entries, records: Records,
    txn: Txn, idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:  # fmt: skip
    """Ask a reviewer to look again at one score: the person analysed, their unit's managers, owners and admins."""

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.raise_dispute(principal, analysis_id, body, request, analyses=analyses,
                                          recordings=recordings, people=people, scores=scores, disputes=disputes,
                                          entries=entries, transactions=txn)  # fmt: skip
        return 201, out.model_dump(mode="json")

    route = service.ROUTE.replace("{analysis_id}", analysis_id)
    return await idempotent(records, key=idempotency_key, route=route, body=body, handler=handler)


@router.get("/v1/disputes", response_model=service.DisputePage)
async def dispute_queue(
    principal: Caller, disputes: Disputes, recordings: Recordings, people: People, units: Units, scores: Scores,
    status: Literal["open", "accepted", "rejected"] = "open", cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> service.DisputePage:  # fmt: skip
    """Disputes you may decide, newest first. Reviewers, managers and administrators only."""
    return await service.dispute_queue(principal, status=status, cursor=cursor, limit=limit, disputes=disputes,
                                       recordings=recordings, people=people, units=units, scores=scores)  # fmt: skip


@router.post("/v1/disputes/{dispute_id}/resolve", response_model=service.DisputeOut)
async def resolve(
    dispute_id: str, body: service.ResolutionIn, request: Request, principal: Caller, disputes: Disputes,
    analyses: Analyses, scores: Scores, outbox: Outbox, entries: Entries, txn: Txn,
) -> service.DisputeOut:  # fmt: skip
    """Accept (with the final score) or reject a dispute, with a note; never one you raised."""
    return await service.resolve(principal, dispute_id, body, request, disputes=disputes, analyses=analyses,
                                 scores=scores, outbox=outbox, entries=entries, transactions=txn)  # fmt: skip
