"""How a recording went through the pipeline, for owners and admins (plan task P7.8).

GET /v1/recordings/{id}/processing: every stage run (attempt, outcome, timing, the error in plain words), the latest
failure with whether it can still be retried (sabha_api.services.retry), and the LLM calls' recorded cost. Costs are
the ones the gateway stored (golden rule 6): calls without a price are counted, never estimated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from sabha_api.auth import Principal
from sabha_api.errors import ForbiddenError
from sabha_api.services.results import visible_recording
from sabha_api.services.retry import ALLOWED
from sabha_core.models import DeadLetter, LlmCall, Person, Recording, StageRun
from sabha_core.reasons import explain
from sabha_core.repo import TenantRepo
from sabha_core.state import RecordingStatus


class StageOut(BaseModel):
    stage: str
    attempt: int
    status: str  # running, succeeded, failed
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None  # in plain words
    error_code: str | None


class FailureOut(BaseModel):
    stage: str
    error: str
    error_code: str
    attempts: int
    at: datetime
    state: Literal["open", "retried", "closed"]


class AiCostOut(BaseModel):
    calls: int
    cost_usd: float | None  # the sum of the priced calls; None when no call had a price
    unpriced_calls: int


class ProcessingOut(BaseModel):
    stages: list[StageOut]
    failure: FailureOut | None
    can_retry: bool
    ai: AiCostOut


async def processing(
    principal: Principal, recording_id: str, *, recordings: TenantRepo[Recording], people: TenantRepo[Person],
    runs: TenantRepo[StageRun], dlq: TenantRepo[DeadLetter], llm_calls: TenantRepo[LlmCall],
) -> ProcessingOut:  # fmt: skip
    if principal.role not in ALLOWED:
        raise ForbiddenError("Only owners and administrators can see how a recording was processed.")
    recording = await visible_recording(principal, recording_id, recordings, people)
    stages = await runs.find({"recording_id": recording.id}, sort=[("started_at", 1), ("attempt", 1)])
    letters = await dlq.find({"recording_id": recording.id}, sort=[("created_at", -1)], limit=1)
    calls = await llm_calls.find({"recording_id": recording.id})
    failure = None
    if letters:
        letter = letters[0]
        state: Literal["open", "retried", "closed"] = (
            "retried" if letter.replayed_at else "closed" if letter.abandoned_at else "open"
        )
        failure = FailureOut(stage=letter.stage, error=explain(letter.error_code), error_code=letter.error_code,
                             attempts=letter.attempts, at=letter.created_at, state=state)  # fmt: skip
    priced = [c.cost_usd for c in calls if c.cost_usd is not None]
    return ProcessingOut(
        stages=[
            StageOut(
                stage=r.stage,
                attempt=r.attempt,
                status=r.status,
                started_at=r.started_at,
                finished_at=r.finished_at,
                duration_ms=r.duration_ms,
                error=explain(r.error_code) if r.error_code else None,
                error_code=r.error_code,
            )
            for r in stages
        ],
        failure=failure,
        can_retry=recording.status is RecordingStatus.FAILED and failure is not None and failure.state == "open",
        ai=AiCostOut(
            calls=len(calls), cost_usd=sum(priced) if priced else None, unpriced_calls=len(calls) - len(priced)
        ),
    )
