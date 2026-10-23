"""Reviews (sabha_api.services.reviews, ADR 0007)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.routers.results import artefact_reader
from sabha_api.services import results
from sabha_api.services import reviews as service
from sabha_core.models import Analysis, AuditEntry, OutboxEvent, Person, Recording, Transcript
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["reviews"])

Caller = Annotated[Principal, Depends(current_principal)]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Analyses = Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))]
Transcripts = Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))]
Reader = Annotated[results.ArtefactReader, Depends(artefact_reader)]


@router.get("/v1/reviews", response_model=results.RecordingPage)
async def review_queue(
    principal: Caller, recordings: Recordings, people: People, analyses: Analyses,
    cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> results.RecordingPage:  # fmt: skip
    """Recordings waiting for a person's decision that you may see, newest first. Reviewers, managers and
    administrators only."""
    return await service.review_queue(principal, cursor=cursor, limit=limit, recordings=recordings, people=people,
                                      analyses=analyses)  # fmt: skip


@router.get("/v1/recordings/{recording_id}/speakers", response_model=service.SpeakersOut)
async def speakers(
    recording_id: str, principal: Caller, recordings: Recordings, people: People, transcripts: Transcripts,
    reader: Reader,
) -> service.SpeakersOut:  # fmt: skip
    """Each speaker with their talk time, Sabha's best guess at their role and a few sample lines, for a reviewer
    to say who is who."""
    return await service.speakers(principal, recording_id, recordings=recordings, people=people,
                                  transcripts=transcripts, reader=reader)  # fmt: skip


@router.post("/v1/recordings/{recording_id}/review", response_model=service.ReviewOut)
async def review(
    recording_id: str, body: service.ReviewIn, request: Request, principal: Caller, recordings: Recordings,
    people: People, transcripts: Transcripts,
    outbox: Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))],
    entries: Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))],
    txn: Annotated[Transactions, Depends(transactions)],
) -> service.ReviewOut:  # fmt: skip
    """Resolve a recording that needs review: confirm who the staff member is (unclear roles; it is then scored), or
    close it as not usable (with a note). Audited."""
    return await service.resolve(principal, recording_id, body, request, recordings=recordings, people=people,
                                 transcripts=transcripts, outbox=outbox, entries=entries, transactions=txn)  # fmt: skip
