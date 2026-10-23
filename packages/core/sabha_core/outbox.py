"""Writing a status change and its event together (plan task P2.5, the transactional outbox).

`record_transition(recordings, outbox, recording_id, from_status, to_status, session=..., ...)` runs
sabha_core.state.transition and inserts the returned event into the `outbox` collection with the same session, so
inside a transaction both happen or neither does. The relay (apps/workers/sabha_workers/relay.py) then publishes
the event: it starts the next pipeline stage and pushes it to live views.

`record_event` writes an event that is not a status change, such as `recording.ready` when a held recording
(unconfirmed duplicate, missing consent) is released for processing.

A session is required: an event written outside the status change's transaction could disagree with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.client_session import ClientSession

from sabha_core.models import OutboxEvent, Recording
from sabha_core.repo import SyncTenantRepo, TenantRepo
from sabha_core.state import RecordingStatus, transition, transition_async

READY = "recording.ready"


def record_transition(
    recordings: SyncTenantRepo[Recording],
    outbox: SyncTenantRepo[OutboxEvent],
    recording_id: str,
    from_status: RecordingStatus | str,
    to_status: RecordingStatus | str,
    *,
    session: ClientSession,
    reason: str,
    meta: Mapping[str, Any] | None = None,
    reanalysis: bool = False,
    review: bool = False,
) -> OutboxEvent:
    event = transition(
        recordings, recording_id, from_status, to_status, reason=reason, meta=meta, reanalysis=reanalysis,
        review=review, session=session,
    )  # fmt: skip
    return outbox.insert_one(event, session=session)


async def record_transition_async(
    recordings: TenantRepo[Recording],
    outbox: TenantRepo[OutboxEvent],
    recording_id: str,
    from_status: RecordingStatus | str,
    to_status: RecordingStatus | str,
    *,
    session: AsyncClientSession,
    reason: str,
    meta: Mapping[str, Any] | None = None,
    reanalysis: bool = False,
    review: bool = False,
) -> OutboxEvent:
    event = await transition_async(
        recordings, recording_id, from_status, to_status, reason=reason, meta=meta, reanalysis=reanalysis,
        review=review, session=session,
    )  # fmt: skip
    return await outbox.insert_one(event, session=session)


async def record_event_async(
    outbox: TenantRepo[OutboxEvent],
    event_type: str,
    payload: Mapping[str, Any],
    *,
    session: AsyncClientSession,
) -> OutboxEvent:
    return await outbox.insert_one(OutboxEvent(type=event_type, payload=dict(payload)), session=session)
