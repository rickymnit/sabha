"""Sending pipeline tasks to Celery (plan task P2.4): used by the relay (P2.5) and the stuck-job sweeper."""

from __future__ import annotations

from celery import Celery

from sabha_core.models import OutboxEvent
from sabha_workers.celery_app import TASK_QUEUES


class CeleryDispatcher:
    def __init__(self, app: Celery) -> None:
        self._app = app

    def send(self, task: str, event: OutboxEvent) -> None:
        """Enqueue `task` for the event's recording; the task id names the event, for tracing and deduplication."""
        recording_id = str(event.payload["recording_id"])
        self.send_stage(task, event.tenant_id, recording_id, task_id=f"{event.id}.{task}", event_id=event.id)

    def send_stage(
        self, task: str, tenant_id: str, recording_id: str, *, task_id: str | None = None, event_id: str | None = None
    ) -> None:
        name = f"sabha.{task}"
        kwargs = {"tenant_id": tenant_id, "recording_id": recording_id}
        if event_id is not None:
            kwargs["event_id"] = event_id  # notify keys its emails by event, so a retry never sends twice
        self._app.send_task(name, kwargs=kwargs, queue=TASK_QUEUES[name], task_id=task_id)
