"""Tests for sabha_asr.batcher: grouping ASR chunk requests from several jobs into GPU batches (P3.5).

Most tests drive the batcher by hand (`run_due`) with a fake clock, so timing is exact. A few run the background
thread with the real clock and only check lower bounds and routing, which cannot flake.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from concurrent.futures import CancelledError, Future

import pytest

from sabha_asr.batcher import DEFAULT_MAX_WAIT_S, Batcher


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Recorder:
    """A process_batch that records every batch and returns each item upper-cased."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def __call__(self, items: Sequence[str]) -> list[str]:
        self.batches.append(list(items))
        return [item.upper() for item in items]


def make(max_batch_size: int = 4, max_wait_s: float = 2.0) -> tuple[Batcher[str, str], Recorder, FakeClock]:
    clock, recorder = FakeClock(), Recorder()
    return Batcher(recorder, max_batch_size=max_batch_size, max_wait_s=max_wait_s, clock=clock), recorder, clock


def test_default_max_wait_is_two_seconds() -> None:
    assert DEFAULT_MAX_WAIT_S == 2.0


def test_nothing_runs_before_the_oldest_item_has_waited_max_wait() -> None:
    batcher, recorder, clock = make()
    future = batcher.submit("job-a", "a1")
    clock.now = 1.0
    batcher.submit("job-b", "b1")
    assert batcher.seconds_until_due() == pytest.approx(1.0)
    clock.now = 1.999
    assert batcher.run_due() == 0
    assert recorder.batches == []
    assert not future.done()
    clock.now = 2.0  # the oldest item (submitted at 0) has now waited max_wait: everything queued goes
    assert batcher.run_due() == 1
    assert recorder.batches == [["a1", "b1"]]
    assert future.result(timeout=0) == "A1"
    assert batcher.seconds_until_due() is None


def test_full_batch_runs_immediately() -> None:
    batcher, recorder, _ = make(max_batch_size=3)
    for item in ("a1", "a2", "b1", "b2"):
        batcher.submit(item[0], item)
    assert batcher.seconds_until_due() == 0.0
    assert batcher.run_due() == 1  # one full batch; the leftover item waits for max_wait
    assert recorder.batches == [["a1", "a2", "b1"]]
    assert batcher.pending() == 1


def test_flush_runs_everything_now() -> None:
    batcher, recorder, _ = make(max_batch_size=2)
    for item in ("a1", "a2", "a3"):
        batcher.submit("a", item)
    assert batcher.flush() == 2
    assert recorder.batches == [["a1", "a2"], ["a3"]]


def test_per_job_order_is_preserved_and_results_go_back_to_the_right_job() -> None:
    batcher, recorder, clock = make(max_batch_size=3)
    futures: dict[str, list[Future[str]]] = {"a": [], "b": []}
    for item in ("a1", "b1", "a2", "a3", "b2", "a4", "b3"):
        futures[item[0]].append(batcher.submit(item[0], item))
    clock.now = 5.0
    batcher.run_due()
    assert recorder.batches == [["a1", "b1", "a2"], ["a3", "b2", "a4"], ["b3"]]
    assert [f.result(timeout=0) for f in futures["a"]] == ["A1", "A2", "A3", "A4"]
    assert [f.result(timeout=0) for f in futures["b"]] == ["B1", "B2", "B3"]


def test_exception_fails_only_that_batch() -> None:
    clock = FakeClock()
    calls: list[list[str]] = []

    def process(items: Sequence[str]) -> list[str]:
        calls.append(list(items))
        if "bad" in items:
            raise RuntimeError("CUDA out of memory")
        return [item.upper() for item in items]

    batcher: Batcher[str, str] = Batcher(process, max_batch_size=2, clock=clock)
    ok_before = [batcher.submit("a", "a1"), batcher.submit("b", "b1")]
    failed = [batcher.submit("a", "a2"), batcher.submit("c", "bad")]
    ok_after = [batcher.submit("b", "b2")]
    clock.now = 2.0
    assert batcher.run_due() == 3
    assert [f.result(timeout=0) for f in ok_before + ok_after] == ["A1", "B1", "B2"]
    for future in failed:
        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            future.result(timeout=0)


def test_wrong_number_of_results_fails_the_batch() -> None:
    batcher: Batcher[str, str] = Batcher(lambda items: ["only one"], max_batch_size=2, clock=FakeClock())
    futures = [batcher.submit("a", "a1"), batcher.submit("a", "a2")]
    batcher.run_due()
    for future in futures:
        with pytest.raises(ValueError, match="2 items"):
            future.result(timeout=0)


def test_cancelled_request_is_left_out_of_the_batch() -> None:
    batcher, recorder, _ = make(max_batch_size=2)
    cancelled = batcher.submit("a", "a1")
    kept = batcher.submit("b", "b1")
    assert cancelled.cancel()
    batcher.flush()
    assert recorder.batches == [["b1"]]
    assert kept.result(timeout=0) == "B1"


def test_stop_without_drain_cancels_waiting_requests() -> None:
    batcher, recorder, _ = make()
    future = batcher.submit("a", "a1")
    batcher.stop(drain=False)
    with pytest.raises(CancelledError):
        future.result(timeout=0)
    assert recorder.batches == []
    with pytest.raises(RuntimeError, match="stopped"):
        batcher.submit("a", "a2")


def test_stop_with_drain_runs_waiting_requests() -> None:
    batcher, _, _ = make()
    future = batcher.submit("a", "a1")
    batcher.stop()
    assert future.result(timeout=0) == "A1"


def test_bad_parameters_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_batch_size"):
        Batcher(Recorder(), max_batch_size=0)
    with pytest.raises(ValueError, match="max_wait_s"):
        Batcher(Recorder(), max_wait_s=-1.0)


# --- background thread (real clock) ----------------------------------------------------------------------------


def test_thread_waits_max_wait_for_a_lone_request() -> None:
    recorder = Recorder()
    batcher: Batcher[str, str] = Batcher(recorder, max_batch_size=8, max_wait_s=0.2)
    batcher.start()
    try:
        started = time.monotonic()
        assert batcher.submit("a", "a1").result(timeout=5) == "A1"
        assert time.monotonic() - started >= 0.2
    finally:
        batcher.stop()


def test_thread_flushes_a_full_batch_without_waiting() -> None:
    recorder = Recorder()
    batcher: Batcher[str, str] = Batcher(recorder, max_batch_size=3, max_wait_s=60.0)
    batcher.start()
    try:
        futures = [batcher.submit("a", f"a{i}") for i in range(3)]
        assert [f.result(timeout=5) for f in futures] == ["A0", "A1", "A2"]
    finally:
        batcher.stop()


def test_thread_runs_one_batch_at_a_time_and_routes_results_across_jobs() -> None:
    active = 0
    most_active = 0
    lock = threading.Lock()

    def process(items: Sequence[str]) -> list[str]:
        nonlocal active, most_active
        with lock:
            active += 1
            most_active = max(most_active, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return [item.upper() for item in items]

    batcher: Batcher[str, str] = Batcher(process, max_batch_size=4, max_wait_s=0.01)
    batcher.start()
    results: dict[str, list[str]] = {}

    def job(name: str) -> None:
        futures = [batcher.submit(name, f"{name}-{i}") for i in range(10)]
        results[name] = [f.result(timeout=10) for f in futures]

    threads = [threading.Thread(target=job, args=(name,)) for name in ("x", "y", "z")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    batcher.stop()
    assert most_active == 1  # concurrency 1 per GPU
    for name in ("x", "y", "z"):
        assert results[name] == [f"{name.upper()}-{i}" for i in range(10)]


def test_manual_driving_is_refused_while_the_thread_runs() -> None:
    batcher, _, _ = make()
    batcher.start()
    try:
        with pytest.raises(RuntimeError, match="thread"):
            batcher.run_due()
        with pytest.raises(RuntimeError, match="already"):
            batcher.start()
    finally:
        batcher.stop()
