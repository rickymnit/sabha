"""Live status (sabha_api.services.events, plan task P2.6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from sabha_api.auth import Principal, current_principal
from sabha_api.deps import tenant_repo
from sabha_api.services import events as service
from sabha_core.models import OutboxEvent, Person, Recording
from sabha_core.repo import TenantRepo

router = APIRouter(tags=["events"])


@router.get(
    "/v1/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"}},
)
async def live_events(
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    outbox: Annotated[TenantRepo[OutboxEvent], Depends(tenant_repo("outbox", OutboxEvent))],
    recordings: Annotated[TenantRepo[Recording], Depends(tenant_repo("recordings", Recording))],
    people: Annotated[TenantRepo[Person], Depends(tenant_repo("people", Person))],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Status changes of the recordings you may see, as they happen (text/event-stream). Send Last-Event-ID when
    reconnecting to receive what you missed in the last 5 minutes. 503 live_unavailable: keep polling instead."""
    settings = request.app.state.settings
    pubsub = await service.subscribe(request.app.state.resources.redis, principal.tenant_id)
    body = service.stream(principal, pubsub, last_event_id=last_event_id, outbox=outbox, recordings=recordings,
                          people=people, heartbeat_s=settings.events_heartbeat_s,
                          max_connection_s=settings.events_max_connection_s)  # fmt: skip
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # no proxy buffering of the stream
    return StreamingResponse(body, media_type="text/event-stream", headers=headers)
