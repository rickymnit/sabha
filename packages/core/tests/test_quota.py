"""Monthly audio-hour quotas: thresholds, plan behaviour at 100 %, IST months and one event per threshold."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sabha_core.quota import Plan, QuotaState, crossed, month_bounds, quota_status

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
H = 3600.0


@pytest.mark.parametrize(
    ("used_h", "plan", "state"),
    [
        (0, Plan.PILOT, QuotaState.OK),
        (79.9, Plan.PILOT, QuotaState.OK),
        (80, Plan.PILOT, QuotaState.WARNING),
        (99.9, Plan.GROWTH, QuotaState.WARNING),
        (100, Plan.PILOT, QuotaState.BLOCKED),
        (100, Plan.STARTER, QuotaState.BLOCKED),
        (100, Plan.GROWTH, QuotaState.OVERAGE),
        (150, Plan.GROWTH, QuotaState.OVERAGE),
    ],
)
def test_state_by_share_and_plan(used_h: float, plan: Plan, state: QuotaState) -> None:
    assert quota_status(used_s=used_h * H, allowance_hours=100, plan=plan, now=NOW).state is state


def test_only_blocking_plans_refuse_uploads() -> None:
    assert not quota_status(used_s=100 * H, allowance_hours=100, plan=Plan.PILOT, now=NOW).uploads_allowed
    assert quota_status(used_s=100 * H, allowance_hours=100, plan=Plan.GROWTH, now=NOW).uploads_allowed
    assert quota_status(used_s=90 * H, allowance_hours=100, plan=Plan.PILOT, now=NOW).uploads_allowed


def test_messages_name_the_allowance_and_the_renewal_date() -> None:
    assert quota_status(used_s=0, allowance_hours=40, plan=Plan.PILOT, now=NOW).message() is None
    warning = quota_status(used_s=33 * H, allowance_hours=40, plan=Plan.PILOT, now=NOW).message()
    assert warning == "33 of this month's 40 audio hours are used. The allowance renews on 1 November 2026."
    blocked = quota_status(used_s=40 * H, allowance_hours=40, plan=Plan.PILOT, now=NOW).message()
    assert blocked is not None
    assert "new uploads are paused until 1 November 2026" in blocked
    overage = quota_status(used_s=41 * H, allowance_hours=40, plan=Plan.GROWTH, now=NOW).message()
    assert overage is not None
    assert "billed as overage" in overage


def test_months_follow_india_time() -> None:
    # 31 Oct 19:00 UTC is already 1 Nov 00:30 in India: a new month.
    start, end = month_bounds(datetime(2026, 10, 31, 19, 0, tzinfo=UTC))
    assert start == datetime(2026, 10, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 11, 30, 18, 30, tzinfo=UTC)
    december = month_bounds(datetime(2026, 12, 10, tzinfo=UTC))
    assert december[1] == datetime(2026, 12, 31, 18, 30, tzinfo=UTC)


def test_each_threshold_is_crossed_once() -> None:
    assert crossed(70 * H, 85 * H, 100) == (0.8,)
    assert crossed(85 * H, 95 * H, 100) == ()
    assert crossed(95 * H, 100 * H, 100) == (1.0,)
    assert crossed(70 * H, 120 * H, 100) == (0.8, 1.0)
    assert crossed(120 * H, 130 * H, 100) == ()


@pytest.mark.parametrize(("used_s", "allowance"), [(-1, 10), (0, 0), (0, -5)])
def test_invalid_input_is_refused(used_s: float, allowance: float) -> None:
    with pytest.raises(ValueError):
        quota_status(used_s=used_s, allowance_hours=allowance, plan=Plan.PILOT, now=NOW)
