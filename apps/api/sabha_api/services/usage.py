"""This month's audio hours: the sidebar's plan block and the upload limit (plan tasks P6.2 and P7.2).

- GET /v1/usage: owners and admins. Usage is the original length of the tenant's recordings uploaded this calendar
  month in India time (sabha_core.quota.month_bounds) whose transcription succeeded: a recording that failed
  before it has a transcript is never charged, and re-analysis reuses the transcript, so nothing counts twice.
  The allowance is the tenant's own or its plan's (sabha_core.quota.allowance_for); without one (the pilot) there
  is no quota state.
- `check_uploads` refuses a new upload (422 quota_exhausted) once a blocking plan (Starter) has used its allowance;
  on Growth uploads go on and the extra hours are billed.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from sabha_api.auth import Role
from sabha_api.errors import ApiError
from sabha_core.models import Recording, Tenant, Transcript, utc_now
from sabha_core.quota import QuotaState, QuotaStatus, allowance_for, month_bounds, quota_status
from sabha_core.repo import TenantRepo

ALLOWED = (Role.OWNER, Role.ADMIN)


class QuotaExhaustedError(ApiError):
    status, code, title = 422, "quota_exhausted", "Audio hours used up"


class UsageOut(BaseModel):
    plan: str
    used_hours: float
    allowance_hours: float | None
    state: QuotaState | None  # None when there is no allowance (the pilot)
    message: str | None  # the banner text at 80 % and 100 %
    resets_at: datetime


async def used_ms(
    recordings: TenantRepo[Recording], transcripts: TenantRepo[Transcript], start: datetime, end: datetime
) -> int:
    """Original length of the recordings uploaded in [start, end) that have a transcript."""
    measured = await recordings.find({"created_at": {"$gte": start, "$lt": end}, "duration_ms": {"$ne": None}})
    if not measured:
        return 0
    found = await transcripts.find({"recording_id": {"$in": [r.id for r in measured]}})
    transcribed = {t.recording_id for t in found}
    return sum(r.duration_ms or 0 for r in measured if r.id in transcribed)


async def _status(
    tenant: Tenant, recordings: TenantRepo[Recording], transcripts: TenantRepo[Transcript], now: datetime
) -> tuple[float, QuotaStatus | None]:
    used_s = await used_ms(recordings, transcripts, *month_bounds(now)) / 1000
    allowance = allowance_for(tenant.plan, tenant.audio_hours_allowance)
    if allowance is None:
        return used_s, None
    return used_s, quota_status(used_s=used_s, allowance_hours=allowance, plan=tenant.plan, now=now)


async def summary(
    tenant: Tenant, recordings: TenantRepo[Recording], transcripts: TenantRepo[Transcript], *,
    now: datetime | None = None,
) -> UsageOut:  # fmt: skip
    now = now or utc_now()
    used_s, status = await _status(tenant, recordings, transcripts, now)
    if status is None:
        return UsageOut(plan=tenant.plan, used_hours=used_s / 3600, allowance_hours=None, state=None, message=None,
                        resets_at=month_bounds(now)[1])  # fmt: skip
    return UsageOut(plan=tenant.plan, used_hours=status.used_hours, allowance_hours=status.allowance_hours,
                    state=status.state, message=status.message(), resets_at=status.resets_at)  # fmt: skip


async def check_uploads(tenant: Tenant, recordings: TenantRepo[Recording], transcripts: TenantRepo[Transcript]) -> None:
    """Raises QuotaExhaustedError when this month's hours are used up on a plan that blocks (sabha_core.quota)."""
    _, status = await _status(tenant, recordings, transcripts, utc_now())
    if status is not None and not status.uploads_allowed:
        raise QuotaExhaustedError(status.message() or "This month's audio hours are used up.")
