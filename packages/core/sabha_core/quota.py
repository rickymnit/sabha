"""Monthly audio-hour quotas (plan task P7.2).

Each tenant has a monthly allowance of audio hours, set by a Sabha admin with its plan (P7.x admin pages); nothing
here invents a number. Usage is the audio duration of the tenant's recordings that started processing this month.

- At WARN_SHARE (80 %) of the allowance the tenant is warned (an event and a banner), once per month.
- At 100 % the plan decides: pilot and starter block new uploads with a clear message; growth allows them and
  meters the overage for billing.

Months are calendar months in India Standard Time, the tenants' own calendar; timestamps stay UTC in storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

from sabha_core.profiles import ConversationType

IST = timezone(timedelta(hours=5, minutes=30), "IST")
WARN_SHARE = 0.8


class Plan(StrEnum):
    PILOT = "pilot"
    STARTER = "starter"
    GROWTH = "growth"


class OverLimit(StrEnum):
    BLOCK = "block"
    METER = "meter"


# How many conversation types a tenant may have switched on at once: "Starter covers any two; Growth covers all five",
# and the free pilot covers all five (docs/design/source/Setup.dc.html, Plans.dc.html).
MAX_TYPES: dict[Plan, int] = {
    Plan.PILOT: len(ConversationType),
    Plan.STARTER: 2,
    Plan.GROWTH: len(ConversationType),
}

OVER_LIMIT: dict[Plan, OverLimit] = {
    Plan.PILOT: OverLimit.BLOCK,
    Plan.STARTER: OverLimit.BLOCK,
    Plan.GROWTH: OverLimit.METER,
}


class QuotaState(StrEnum):
    OK = "ok"
    WARNING = "warning"  # at or past 80 %, under 100 %
    BLOCKED = "blocked"  # at or past 100 % on a blocking plan: no new uploads
    OVERAGE = "overage"  # at or past 100 % on a metering plan: uploads allowed, overage billed


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    state: QuotaState
    used_hours: float
    allowance_hours: float
    resets_at: datetime  # start of next month, IST, as a UTC timestamp

    @property
    def used_share(self) -> float:
        return self.used_hours / self.allowance_hours

    @property
    def uploads_allowed(self) -> bool:
        return self.state is not QuotaState.BLOCKED

    def message(self) -> str | None:
        """The text for the banner or the refused upload; None when there is nothing to say."""
        local = self.resets_at.astimezone(IST)
        resets = f"{local.day} {local:%B %Y}"
        used, allowance = _hours(self.used_hours), _hours(self.allowance_hours)
        match self.state:
            case QuotaState.OK:
                return None
            case QuotaState.WARNING:
                return f"{used} of this month's {allowance} audio hours are used. The allowance renews on {resets}."
            case QuotaState.BLOCKED:
                return (
                    f"This month's {allowance} audio hours are used up, so new uploads are paused until {resets}. "
                    "Ask your Sabha contact to raise the allowance if you need more."
                )
            case QuotaState.OVERAGE:
                return f"This month's {allowance} audio hours are used up; further hours are billed as overage."


def _hours(value: float) -> str:
    return f"{value:.1f}".removesuffix(".0")


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """The current IST calendar month as [start, end) UTC timestamps."""
    local = now.astimezone(IST)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.astimezone(UTC), end.astimezone(UTC)


def quota_status(*, used_s: float, allowance_hours: float, plan: Plan, now: datetime) -> QuotaStatus:
    if allowance_hours <= 0:
        raise ValueError("allowance_hours must be positive")
    if used_s < 0:
        raise ValueError("used_s must not be negative")
    used_hours = used_s / 3600
    share = used_hours / allowance_hours
    if share >= 1:
        state = QuotaState.BLOCKED if OVER_LIMIT[plan] is OverLimit.BLOCK else QuotaState.OVERAGE
    elif share >= WARN_SHARE:
        state = QuotaState.WARNING
    else:
        state = QuotaState.OK
    return QuotaStatus(state, used_hours, allowance_hours, month_bounds(now)[1])


def crossed(before_s: float, after_s: float, allowance_hours: float) -> tuple[float, ...]:
    """The thresholds (0.8, 1.0) that usage passed going from `before_s` to `after_s`: each emits one event."""
    limit_s = allowance_hours * 3600
    return tuple(t for t in (WARN_SHARE, 1.0) if before_s < t * limit_s <= after_s)
