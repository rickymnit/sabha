"""Fair GPU scheduling (P7.2): weighted deficit round robin per tenant, a short-recording lane, no starvation."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

import pytest

from sabha_workers.fair_scheduler import Chunk, FairScheduler, estimate_completion_s


def chunks(tenant: str, recording: str, count: int, *, duration_s: float, cost_s: float = 30.0) -> list[Chunk]:
    return [Chunk(f"{recording}#{i}", tenant, recording, cost_s, duration_s) for i in range(count)]


def drain(scheduler: FairScheduler, limit: int = 10_000) -> list[Chunk]:
    out = []
    while (chunk := scheduler.next()) is not None and len(out) < limit:
        out.append(chunk)
    return out


def test_empty_scheduler_returns_none() -> None:
    assert FairScheduler().next() is None


def test_chunks_of_one_recording_keep_their_order() -> None:
    s = FairScheduler()
    for c in chunks("A", "rec-a", 5, duration_s=3600):
        s.submit(c)
    assert [c.chunk_id for c in drain(s)] == [f"rec-a#{i}" for i in range(5)]


def test_a_short_call_jumps_a_bulk_upload_from_another_tenant() -> None:
    # Tenant A uploaded twenty 1-hour lessons (120 chunks each); tenant B then uploads one 5-minute call.
    s = FairScheduler()
    for n in range(20):
        for c in chunks("A", f"lesson-{n}", 120, duration_s=3600):
            s.submit(c)
    for _ in range(10):
        s.next()  # the GPU is already busy with A's backlog
    for c in chunks("B", "call-1", 10, duration_s=300):
        s.submit(c)
    order = drain(s)
    b_positions = [i for i, c in enumerate(order) if c.tenant_id == "B"]
    # B's call is in the short lane: all of its chunks go before A continues (A is in the normal lane, which gets
    # one turn after every 3 short picks), so B finishes within its own 10 chunks plus 3 of A's.
    assert b_positions[0] == 0
    assert b_positions[-1] <= 10 + 3


def test_tenants_in_the_same_lane_share_by_weight() -> None:
    s = FairScheduler(weights={"A": 2.0, "B": 1.0})
    for c in chunks("A", "rec-a", 600, duration_s=3600):
        s.submit(c)
    for c in chunks("B", "rec-b", 600, duration_s=3600):
        s.submit(c)
    first = [s.next() for _ in range(300)]
    share = Counter(c.tenant_id for c in first if c is not None)
    assert share["A"] == 200 and share["B"] == 100  # exactly 2:1 with equal chunk costs


def test_one_tenants_backlog_does_not_block_another_in_the_normal_lane() -> None:
    s = FairScheduler()
    for c in chunks("A", "big", 500, duration_s=3600):
        s.submit(c)
    for c in chunks("B", "lesson", 4, duration_s=2700):
        s.submit(c)
    order = drain(s)
    b_positions = [i for i, c in enumerate(order) if c.tenant_id == "B"]
    assert b_positions == [1, 3, 5, 7]  # alternating, not after A's 500 chunks


def test_long_recordings_are_never_starved_by_a_stream_of_short_ones() -> None:
    s = FairScheduler(short_burst=3)
    for c in chunks("A", "lesson", 5, duration_s=3600):
        s.submit(c)
    picks = []
    for n in range(40):
        for c in chunks("B", f"call-{n}", 1, duration_s=120):
            s.submit(c)
        picks.append(s.next())
    normal = [i for i, c in enumerate(picks) if c is not None and c.tenant_id == "A"]
    assert normal and normal[0] <= 3
    assert all(b - a <= 4 for a, b in pairwise(normal))


def test_large_chunks_wait_for_enough_deficit_but_are_not_lost() -> None:
    s = FairScheduler(quantum_s=30.0)
    s.submit(Chunk("big#0", "A", "big", 90.0, 3600))
    s.submit(Chunk("small#0", "B", "small", 30.0, 3600))
    order = [c.chunk_id for c in drain(s)]
    assert sorted(order) == ["big#0", "small#0"]


def test_unknown_tenants_get_weight_one_and_weights_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FairScheduler(weights={"A": 0})
    s = FairScheduler(weights={"A": 1.0})
    s.submit(Chunk("x#0", "Z", "x", 30.0, 60))
    assert s.next() is not None


def test_completion_estimate_from_backlog_and_measured_throughput() -> None:
    # 2 hours of audio queued, the GPU processes 20 audio seconds per wall second: 360 s, plus this recording's own
    # 300 s at the same speed: 15 s.
    assert estimate_completion_s(backlog_audio_s=7200, recording_audio_s=300, audio_s_per_wall_s=20.0) == 375.0
    with pytest.raises(ValueError):
        estimate_completion_s(backlog_audio_s=1, recording_audio_s=1, audio_s_per_wall_s=0)
