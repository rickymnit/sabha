"""This month's audio hours for the sidebar's plan block (plan tasks P6.2 and P7.2).

GET /v1/usage: owners and admins. Usage is the measured duration of the tenant's recordings uploaded this calendar
month in India time (sabha_core.quota.month_bounds); a recording counts once preprocessing has measured it, and
re-analysis never counts it again. The allowance is the one Sabha set on the tenant, or null: the API never
invents one (golden rule 6), so without it there is no quota state either.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from sabha_api.auth import Role
from sabha_core.models import Recording, Tenant, utc_now
from sabha_core.quota import QuotaState, month_bounds, quota_status
from sabha_core.repo import TenantRepo

ALLOWED = (Role.OWNER, Role.ADMIN)


class UsageOut(BaseModel):
    plan: str
    used_hours: float
    allowance_hours: float | None
    state: QuotaState | None  # None when no allowance is set
    message: str | None  # the banner text at 80 % and 100 %
    resets_at: datetime


async def used_ms(recordings: TenantRepo[Recording], start: datetime, end: datetime) -> int:
    rows = await recordings.aggregate([
        {"$match": {"created_at": {"$gte": start, "$lt": end}, "duration_ms": {"$ne": None}}},
        {"$group": {"_id": None, "ms": {"$sum": "$duration_ms"}}},
    ])  # fmt: skip
    return int(rows[0]["ms"]) if rows else 0


async def summary(tenant: Tenant, recordings: TenantRepo[Recording], *, now: datetime | None = None) -> UsageOut:
    now = now or utc_now()
    start, end = month_bounds(now)
    used_s = await used_ms(recordings, start, end) / 1000
    allowance = tenant.audio_hours_allowance
    if allowance is None:
        return UsageOut(plan=tenant.plan, used_hours=used_s / 3600, allowance_hours=None, state=None, message=None,
                        resets_at=end)  # fmt: skip
    status = quota_status(used_s=used_s, allowance_hours=allowance, plan=tenant.plan, now=now)
    return UsageOut(plan=tenant.plan, used_hours=status.used_hours, allowance_hours=allowance, state=status.state,
                    message=status.message(), resets_at=status.resets_at)  # fmt: skip
