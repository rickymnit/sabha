"""Phone calls from MyOperator (ADR 0017). Logic in sabha_api.services.phone_calls."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from sabha_api.auth import Principal, require_role
from sabha_api.auth.directory import Directory, directory
from sabha_api.deps import Transactions, tenant_repo, transactions
from sabha_api.errors import NotFoundError
from sabha_api.idempotency import HEADER, idempotent
from sabha_api.services import costs, usage
from sabha_api.services import phone_calls as service
from sabha_core.models import (
    Analysis,
    AuditEntry,
    IdempotencyRecord,
    OutboxEvent,
    Person,
    PhoneCall,
    Recording,
    Transcript,
    Unit,
)
from sabha_core.repo import TenantRepo

router = APIRouter(prefix="/v1/phone-calls", tags=["phone calls"])

Caller = Annotated[Principal, Depends(require_role(*service.ALLOWED))]
Calls = Annotated[TenantRepo[PhoneCall], Depends(tenant_repo("phone_calls", PhoneCall))]
People = Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))]
Recordings = Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))]
Entries = Annotated[TenantRepo[AuditEntry], Depends(tenant_repo("audit_log", AuditEntry))]


@router.get("", response_model=service.PhoneCallPage)
async def list_phone_calls(
    request: Request,
    principal: Caller,
    calls: Calls,
    people: People,
    recordings: Recordings,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = 50,
    agent: Annotated[str | None, Query(description="The MyOperator user id of the agent who answered first")] = None,
    direction: Literal["incoming", "outgoing"] | None = None,
    analysed: bool | None = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> service.PhoneCallPage:
    """Answered, recorded calls from MyOperator, newest first: owners and admins see all, managers their units'."""
    service.check_set_up(principal, request.app.state.settings)
    return await service.list_calls(
        principal,
        calls=calls,
        people=people,
        recordings=recordings,
        cursor=cursor,
        limit=limit,
        agent=agent,
        direction=direction,
        analysed=analysed,
        since=since,
        until=until,
    )


@router.get("/agents", response_model=list[service.AgentOption])
async def phone_agents(request: Request, principal: Caller, calls: Calls, people: People) -> list[service.AgentOption]:
    """The agents who answered the calls the caller may see, and who each is matched to in Sabha."""
    service.check_set_up(principal, request.app.state.settings)
    return await service.agents(principal, calls=calls, people=people)


@router.get("/{call_id}/audio", response_model=service.AudioOut)
async def phone_call_audio(
    call_id: str, request: Request, principal: Caller, calls: Calls, entries: Entries
) -> service.AudioOut:
    """A link to the call's recording at MyOperator, valid for 24 hours. Audited as phone_call.play."""
    service.check_set_up(principal, request.app.state.settings)
    return await service.audio(
        principal, call_id, request, settings=request.app.state.settings, calls=calls, entries=entries
    )


@router.post(
    "/{call_id}/analyse",
    status_code=201,
    response_model=service.AnalyseOut,
    responses={409: {"description": "`already_analysed` (with `recording_id`)"}},
)
async def analyse_phone_call(
    call_id: str,
    body: service.AnalyseIn,
    request: Request,
    principal: Caller,
    found: Annotated[Directory, Depends(directory)],
    calls: Calls,
    people: People,
    units: Annotated[TenantRepo[Unit], Depends(tenant_repo("units", Unit))],
    recordings: Recordings,
    entries: Entries,
    outbox: Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))],
    transcripts: Annotated[TenantRepo[Transcript], Depends(tenant_repo("transcripts", Transcript))],
    analyses: Annotated[TenantRepo[Analysis], Depends(tenant_repo("analyses", Analysis))],
    records: Annotated[TenantRepo[IdempotencyRecord], Depends(tenant_repo("idempotency_keys", IdempotencyRecord))],
    txn: Annotated[Transactions, Depends(transactions)],
    idempotency_key: Annotated[str | None, Header(alias=HEADER)] = None,
) -> JSONResponse:
    """Analyse this call: its audio is fetched from MyOperator and it goes through the pipeline like an upload.
    Refused (422 quota_exhausted) once a Starter plan's audio hours for the month are used up."""
    settings = request.app.state.settings
    service.check_set_up(principal, settings)

    async def handler() -> tuple[int, dict[str, object]]:
        tenant = await found.tenant(principal.tenant_id)
        if tenant is None:
            raise NotFoundError("Your organisation could not be found.")
        await usage.check_uploads(tenant, recordings, transcripts)
        call = await calls.find_one({"_id": call_id, **service.visible(principal)})
        estimate = None
        if call is not None and call.duration_s > 0 and body.type in service.PHONE_TYPES:
            estimate = await costs.estimate(
                body.type,
                call.duration_s * 1000,
                settings,
                recordings=recordings,
                analyses=analyses,
                asr_spec=body.asr_model,
            )
        out = await service.analyse(
            principal,
            call_id,
            body,
            request,
            tenant=tenant,
            settings=settings,
            calls=calls,
            people=people,
            units=units,
            recordings=recordings,
            outbox=outbox,
            entries=entries,
            transactions=txn,
            cost_estimate=estimate,
        )
        return 201, out.model_dump(mode="json")

    route = service.ANALYSE_ROUTE.replace("{call_id}", call_id)
    return await idempotent(records, key=idempotency_key, route=route, body=body, handler=handler)
