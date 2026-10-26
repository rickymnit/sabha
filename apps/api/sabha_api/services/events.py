"""Live status over server-sent events (plan task P2.6): GET /v1/events.

The relay publishes every outbox event to the Redis channel `events:{tenant_id}` (sabha_workers.relay). This route
subscribes to the caller's own tenant channel only, and forwards an event only when the caller may see its recording,
by the recordings list's own filter (sabha_api.services.results.visible_filter: owners and admins all, managers and
reviewers their units, staff their own). Each message carries only what a page needs to refresh itself: the event
type, the recording, its new status, the reason code and the time; never the event's meta (review notes, reasons
for a re-analysis).

The stream:

- `: connected` once subscribed, so a client knows the stream works;
- with a Last-Event-ID header, first the events published after that one, from the outbox, but no further back than
  REPLAY_WINDOW (5 minutes; an unknown id replays the whole window), in order;
- then live events, as `id`, `event: status` and `data` (JSON) lines; an event already replayed is not sent again;
- a `: ping` comment every `events_heartbeat_s` (15 s) while nothing happens, so proxies keep the connection open;
- the server ends the stream after `events_max_connection_s` (5 minutes); the client reconnects with Last-Event-ID.

Without Redis the route answers 503 `live_unavailable` before streaming, and the web app keeps polling.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

from sabha_api.auth import Principal
from sabha_api.errors import ApiError
from sabha_api.services.results import visible_filter
from sabha_core.models import OutboxEvent, Person, Recording, utc_now
from sabha_core.repo import TenantRepo

REPLAY_WINDOW = timedelta(minutes=5)
REPLAY_LIMIT = 500


class LiveUnavailableError(ApiError):
    status, code, title = 503, "live_unavailable", "Live updates are not available"


def channel(tenant_id: str) -> str:
    return f"events:{tenant_id}"


async def subscribe(redis: Redis | None, tenant_id: str) -> PubSub:
    """Subscribe to the tenant's channel, or raise LiveUnavailableError (before any byte is streamed)."""
    if redis is None:
        raise LiveUnavailableError("Live updates are not available right now.")
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel(tenant_id))
    except (RedisError, OSError) as exc:
        await pubsub.aclose()
        raise LiveUnavailableError("Live updates are not available right now.") from exc
    return pubsub


def message(event_id: str, event_type: str, payload: dict[str, Any], at: str) -> str:
    data = {"type": event_type, "recording_id": payload.get("recording_id"), "status": payload.get("to_status"),
            "reason": payload.get("reason"), "at": at}  # fmt: skip
    return f"id: {event_id}\nevent: status\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _replay(outbox: TenantRepo[OutboxEvent], last_event_id: str) -> list[OutboxEvent]:
    floor = utc_now() - REPLAY_WINDOW
    last = await outbox.find_one({"_id": last_event_id})
    since = max(last.created_at, floor) if last is not None else floor
    query = {"created_at": {"$gt": since}, "published_at": {"$ne": None}}
    return await outbox.find(query, sort=[("created_at", 1), ("_id", 1)], limit=REPLAY_LIMIT)


async def stream(
    principal: Principal, pubsub: PubSub, *, last_event_id: str | None, outbox: TenantRepo[OutboxEvent],
    recordings: TenantRepo[Recording], people: TenantRepo[Person], heartbeat_s: float, max_connection_s: float,
) -> AsyncIterator[str]:  # fmt: skip
    """The event stream of an already subscribed caller (module docstring). Closes the subscription at the end."""
    scope = await visible_filter(principal, people)
    allowed: dict[str, bool] = {}

    async def visible(recording_id: object) -> bool:
        if not isinstance(recording_id, str):
            return False
        if recording_id not in allowed:
            allowed[recording_id] = await recordings.find_one({"_id": recording_id, **scope}) is not None
        return allowed[recording_id]

    loop = asyncio.get_running_loop()
    try:
        yield ": connected\n\n"
        sent: set[str] = set()
        if last_event_id:
            for event in await _replay(outbox, last_event_id):
                if await visible(event.payload.get("recording_id")):
                    sent.add(event.id)
                    yield message(event.id, event.type, event.payload, event.created_at.isoformat())
        deadline = loop.time() + max_connection_s
        next_beat = loop.time() + heartbeat_s
        while (now := loop.time()) < deadline:
            wait = max(0.0, min(deadline, next_beat) - now)
            raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=wait)
            if raw is not None and raw.get("type") == "message":
                try:
                    item = json.loads(raw["data"])
                except (TypeError, ValueError):
                    item = None
                if (
                    isinstance(item, dict)
                    and item.get("tenant_id") == principal.tenant_id
                    and item.get("id") not in sent
                    and await visible((item.get("payload") or {}).get("recording_id"))
                ):
                    sent.add(str(item["id"]))
                    yield message(str(item["id"]), str(item["type"]), item["payload"], str(item["created_at"]))
            if loop.time() >= next_beat:
                yield ": ping\n\n"
                next_beat = loop.time() + heartbeat_s
    finally:
        try:
            await pubsub.unsubscribe()
        finally:
            await pubsub.aclose()
