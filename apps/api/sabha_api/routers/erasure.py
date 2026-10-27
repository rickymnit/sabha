"""Erasure on request (sabha_api.services.erasure, plan task P7.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.errors import NotReadyError
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import erasure as service
from sabha_core.models import (
    Analysis,
    AuditEntry,
    DeadLetter,
    Dispute,
    IdempotencyRecord,
    IdentityLink,
    LlmCall,
    OutboxEvent,
    Person,
    Recording,
    Score,
    StageRun,
    Transcript,
    User,
)  # fmt: skip
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["erasure"])


Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Users = Annotated[TenantRepo[User], Depends(tenant_repo("users", User))]
Identities = Annotated[TenantRepo[IdentityLink], Depends(tenant_repo("identities", IdentityLink))]
Transcripts = Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Scores = Annotated[TenantRepo[Score], Depends(tenant_repo("scores", Score))]
Disputes = Annotated[TenantRepo[Dispute], Depends(tenant_repo("disputes", Dispute))]
StageRuns = Annotated[TenantRepo[StageRun], Depends(tenant_repo("stage_runs", StageRun))]
Letters = Annotated[TenantRepo[DeadLetter], Depends(tenant_repo("dlq", DeadLetter))]
LlmCalls = Annotated[TenantRepo[LlmCall], Depends(tenant_repo("llm_calls", LlmCall))]
Outbox = Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]
Records = Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))]


@router.post("/v1/erasure", response_model=service.ErasureOut)
async def erase(
    body: service.ErasureIn, request: Request, principal: Annotated[Principal, Depends(current_principal)],
    recordings: Recordings, people: People, users: Users, identities: Identities, transcripts: Transcripts,
    analyses: Analyses, scores: Scores, disputes: Disputes, stage_runs: StageRuns, dlq: Letters, llm_calls: LlmCalls,
    outbox: Outbox, entries: Entries, records: Records,
    txn: Annotated[Transactions, Depends(transactions)],
    idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:  # fmt: skip
    """Erase one recording, or one person with all their recordings and their login (owners). Send confirm=false
    first to see what would be erased."""
    s3 = request.app.state.resources.s3
    if s3 is None:
        raise NotReadyError("Storage is not available.")
    repos: service.Repos = {"recordings": recordings, "people": people, "users": users, "identities": identities,
             "transcripts": transcripts, "analyses": analyses, "scores": scores, "disputes": disputes,
             "stage_runs": stage_runs, "dlq": dlq, "llm_calls": llm_calls, "outbox": outbox}  # fmt: skip

    async def handler() -> tuple[int, dict[str, object]]:
        out = await service.erase(principal, body, request, settings=request.app.state.settings, s3=s3, repos=repos,
                                  entries=entries, transactions=txn)  # fmt: skip
        return 200, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.ROUTE, body=body, handler=handler)
