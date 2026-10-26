"""The outbox relay: turns outbox events into pipeline tasks and live updates (plan task P2.5).

A long-running process (one per deployment) that:
1. watches the `outbox` collection with a MongoDB change stream, and stores where it stopped (resume token) in the
   `relay_state` system collection, so a restart continues where it left off;
2. for each new event, sends the pipeline tasks it routes to (ROUTES), records each task on the event right after
   sending it, publishes the event to the Redis channel `events:{tenant_id}` for live views (P2.6), and marks it
   published;
3. every 10 s also sweeps for events still unpublished after 30 s (missed while the stream was down, or failed).

No duplicate dispatch: before sending, the relay re-reads the event and skips tasks already recorded on it, so a
restart or a sweep never sends a task twice. The only gap is a crash between sending a task and recording it;
then the task is sent again, which is safe because every stage is idempotent (golden rule 3). A failed dispatch
leaves the event unpublished for the sweep to retry. Live updates are best effort: a failed publish is logged and
the event still counts as published (SSE clients replay from the outbox, P2.6).

This module may use SyncSystemRepo (tests/security/test_raw_collection_access.py): it reads every tenant's events.
The Celery dispatcher and the process entry point arrive with P2.4.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from redis import Redis
from redis.exceptions import RedisError

from sabha_core.models import OutboxEvent, RelayState, utc_now
from sabha_core.repo import SyncSystemRepo

log = logging.getLogger("sabha.workers.relay")

STATE_ID = "outbox"
SWEEP_EVERY_S = 10.0
SWEEP_OLDER_THAN = timedelta(seconds=30)
SWEEP_BATCH = 500

ROUTES: dict[str, tuple[str, ...]] = {
    "recording.ready": ("preprocess",),  # a held recording released (duplicate confirmed, consent added)
    "recording.diarizing": ("diarize",),  # preprocessing finished
    "recording.transcribing": ("transcribe",),  # diarization finished
    "recording.analyzing": ("analyze",),  # transcription finished (or re-analysis started)
    "recording.completed": ("notify", "meter"),
    "recording.failed": ("notify",),
    "recording.needs_review": ("notify",),
    "dispute.resolved": ("notify",),  # emails whoever raised the dispute (P6.7)
}


def routes(event: OutboxEvent) -> tuple[str, ...]:
    """The pipeline tasks an event starts. An upload starts preprocessing only if it is ready (not held)."""
    meta = event.payload.get("meta") or {}
    if event.type == "recording.uploaded":
        return ("preprocess",) if meta.get("ready") else ()
    if event.type == "recording.completed" and meta.get("reanalysis"):
        return ()  # quiet (owner's decision, 2026-10-26), and no audio is metered twice
    return ROUTES.get(event.type, ())


class Dispatcher(Protocol):
    def send(self, task: str, event: OutboxEvent) -> None:
        """Enqueue `task` for the event's recording. Raises if the task could not be enqueued."""
        ...


class Publisher(Protocol):
    def publish(self, channel: str, message: str) -> None: ...


class RedisPublisher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def publish(self, channel: str, message: str) -> None:
        self._redis.publish(channel, message)


def live_message(event: OutboxEvent) -> str:
    return json.dumps(
        {
            "id": event.id,
            "type": event.type,
            "tenant_id": event.tenant_id,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        },
        ensure_ascii=False,
    )


class Relay:
    def __init__(
        self,
        outbox: SyncSystemRepo[OutboxEvent],
        state: SyncSystemRepo[RelayState],
        dispatcher: Dispatcher,
        publisher: Publisher,
        *,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._outbox = outbox
        self._state = state
        self._dispatcher = dispatcher
        self._publisher = publisher
        self._now = now

    def handle(self, event_id: str) -> bool:
        """Dispatch and publish one event; False if it was already published (or does not exist)."""
        event = self._outbox.find_one({"_id": event_id})
        if event is None or event.published_at is not None:
            return False
        for task in routes(event):
            if task in event.dispatched:
                continue
            self._dispatcher.send(task, event)
            self._outbox.update_one({"_id": event.id}, {"$addToSet": {"dispatched": task}})
        try:
            self._publisher.publish(f"events:{event.tenant_id}", live_message(event))
        except (RedisError, OSError) as exc:
            log.warning(
                "could not publish a live update", extra={"event_id": event.id, "error_type": type(exc).__name__}
            )
        self._outbox.update_one({"_id": event.id, "published_at": None}, {"$set": {"published_at": self._now()}})
        return True

    def sweep(self, older_than: timedelta = SWEEP_OLDER_THAN) -> int:
        """Handle unpublished events older than `older_than`, oldest first; returns how many were handled."""
        cutoff = self._now() - older_than
        stale = self._outbox.find(
            {"published_at": None, "created_at": {"$lte": cutoff}}, sort=[("created_at", 1)], limit=SWEEP_BATCH
        )
        return sum(self._handle_safely(event.id) for event in stale)

    def _handle_safely(self, event_id: str) -> bool:
        try:
            return self.handle(event_id)
        except Exception as exc:  # one bad event must not stop the relay; the sweep retries it
            log.exception("could not relay an event", extra={"event_id": event_id, "error_type": type(exc).__name__})
            return False

    def run(self, stop: threading.Event, *, sweep_every_s: float = SWEEP_EVERY_S) -> None:
        """Watch the outbox until `stop` is set, resuming from the stored token; sweep periodically."""
        saved = self._state.find_one({"_id": STATE_ID})
        token: dict[str, Any] | None = saved.resume_token if saved else None
        last_sweep = float("-inf")
        with self._outbox.watch_inserts(resume_after=token) as stream:
            while not stop.is_set():
                change = stream.try_next()
                if change is not None:
                    self._handle_safely(str(change["fullDocument"]["_id"]))
                    self._save(stream.resume_token)
                if time.monotonic() - last_sweep >= sweep_every_s:
                    self.sweep()
                    last_sweep = time.monotonic()

    def _save(self, token: dict[str, Any] | None) -> None:
        if token is not None:
            self._state.upsert({"_id": STATE_ID}, {"$set": {"resume_token": token, "updated_at": self._now()}})


def main() -> None:  # pragma: no cover - the process entry point; the parts are tested
    """`python -m sabha_workers.relay`: run the relay until SIGTERM or Ctrl-C."""
    import signal

    from sabha_core.logging import configure_logging
    from sabha_core.mongo import open_sync
    from sabha_core.settings import get_settings
    from sabha_workers.celery_app import create_app
    from sabha_workers.dispatch import CeleryDispatcher

    settings = get_settings()
    configure_logging(settings.log_level)
    client, database = open_sync(settings)
    relay = Relay(
        SyncSystemRepo(database, "outbox", OutboxEvent),
        SyncSystemRepo(database, "relay_state", RelayState),
        CeleryDispatcher(create_app(settings)),
        RedisPublisher(Redis.from_url(settings.redis_url.get_secret_value())),
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    log.info("outbox relay started")
    try:
        relay.run(stop)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
