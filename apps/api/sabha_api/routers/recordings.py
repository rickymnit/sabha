"""Recordings: create with a presigned multipart upload, and fresh part URLs (plan task P2.1).

Logic in sabha_api.services.recordings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.errors import NotFoundError, NotReadyError
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import recordings as service
from sabha_api.services import usage
from sabha_core.models import AuditEntry, IdempotencyRecord, OutboxEvent, Person, Recording, Transcript, Unit
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/recordings", tags=["recordings"])

Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]


def upload_storage(request: Request) -> service.UploadStorage:
    s3 = request.app.state.resources.s3
    if s3 is None:
        raise NotReadyError("Storage is not available.")
    return service.UploadStorage(s3, request.app.state.settings)


Storage = Annotated[service.UploadStorage, Depends(upload_storage)]


@router.post("", status_code=201, response_model=service.UploadOut)
async def create_recording(
    body: service.RecordingIn,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    found: Annotated[Directory, Depends(directory)],
    storage: Storage,
    records: Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))],
    recordings: Recordings,
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
    entries: Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))],
    transcripts: Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))],
    txn: Annotated[Transactions, Depends(transactions)],
    idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:
    """Create a recording and start its upload: PUT each part to its URL, then call complete. Refused (422
    quota_exhausted) once a Starter plan's audio hours for the month are used up."""

    async def handler() -> tuple[int, dict[str, object]]:
        tenant = await found.tenant(principal.tenant_id)
        if tenant is None:
            raise NotFoundError("Your organisation could not be found.")
        await usage.check_uploads(tenant, recordings, transcripts)
        out = await service.create(
            principal,
            body,
            request,
            tenant=tenant,
            settings=request.app.state.settings,
            storage=storage,
            recordings=recordings,
            people=people,
            units=units,
            entries=entries,
            transactions=txn,
        )
        return 201, out.model_dump(mode="json")

    return await idempotent(records, key=idempotency_key, route=service.ROUTE, body=body, handler=handler)


@router.post("/{recording_id}/parts", response_model=service.PartsOut)
async def part_urls(
    recording_id: str,
    body: service.PartsIn,
    principal: Annotated[Principal, Depends(current_principal)],
    storage: Storage,
    recordings: Recordings,
) -> service.PartsOut:
    """Fresh presigned URLs for some parts of an upload still in progress (for resuming)."""
    return await service.part_urls(principal, recording_id, body, storage=storage, recordings=recordings)


@router.post(
    "/{recording_id}/complete",
    response_model=service.CompleteOut,
    responses={409: {"description": "`duplicate_recording` (with `duplicate_of`) or `upload_not_open`"}},
)
async def complete_upload(
    recording_id: str,
    body: service.CompleteIn,
    principal: Annotated[Principal, Depends(current_principal)],
    storage: Storage,
    recordings: Recordings,
    outbox: Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))],
    txn: Annotated[Transactions, Depends(transactions)],
) -> service.CompleteOut:
    """Finish an upload: every part with its ETag, and the file's SHA-256. Safe to retry with the same body."""
    return await service.complete(
        principal, recording_id, body, storage=storage, recordings=recordings, outbox=outbox, transactions=txn
    )
