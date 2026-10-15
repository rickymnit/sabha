"""A small in-process batcher that groups ASR chunk requests from several jobs into GPU batches (plan task P3.5).

One batcher serves one GPU and runs one batch at a time (concurrency 1). Jobs call `submit(job_id, item)` and get a
`concurrent.futures.Future` for that item's result. A batch runs when either:

- `max_batch_size` requests are waiting (it takes the oldest `max_batch_size`), or
- the oldest waiting request has waited `max_wait_s` (it takes everything waiting, up to `max_batch_size`).

Requests leave the queue in submission order and batches run one after another, so each job's chunks are processed
in the order the job submitted them. Each item's result is set on its own future, so results always reach the job
that asked. If `process_batch` raises, or returns the wrong number of results, every request in that batch gets the
exception on its future (and it is logged); other batches are unaffected. Nothing is swallowed or retried here:
retrying is the stage's decision.

Why threads, not asyncio: model inference is blocking code that releases the GIL, and the gpu.speech Celery worker
runs ordinary synchronous tasks. With asyncio every call into the model would still need an executor thread, and the
Celery tasks would need an event loop bridge. With threads, job tasks (Celery's threads pool, one process per GPU)
simply submit and block on their futures, and one batcher thread owns the GPU.

Time is read only through the injected `clock` (seconds, monotonic), so tests can drive the batcher by hand with a
fake clock: `run_due()` runs every batch that is due now in the calling thread, `flush()` runs everything now. The
background thread (`start()`) uses the clock for deadlines but real time for sleeping, so give it a real monotonic
clock. Manual driving and the thread cannot be mixed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_MAX_WAIT_S = 2.0
"""Longest a request waits for others to share its batch (P3.5: max wait 2 s)."""

DEFAULT_MAX_BATCH_SIZE = 8
"""A placeholder until GPU memory is measured with the chosen ASR model on the staging GPU."""


@dataclass(slots=True)
class _Request[T, R]:
    job_id: str
    item: T
    future: Future[R]
    submitted_at: float


class Batcher[T, R]:
    """Groups items from several jobs into batches for `process_batch`, one batch at a time. Thread-safe."""

    def __init__(
        self,
        process_batch: Callable[[Sequence[T]], Sequence[R]],
        *,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        max_wait_s: float = DEFAULT_MAX_WAIT_S,
        clock: Callable[[], float] = time.monotonic,
        name: str = "asr-batcher",
    ) -> None:
        if max_batch_size < 1:
            raise ValueError(f"max_batch_size must be at least 1, got {max_batch_size}")
        if not max_wait_s >= 0:
            raise ValueError(f"max_wait_s cannot be negative, got {max_wait_s}")
        self._process_batch = process_batch
        self._max_batch_size = max_batch_size
        self._max_wait_s = max_wait_s
        self._clock = clock
        self._name = name
        self._lock = threading.Lock()  # guards the queue and flags
        self._changed = threading.Condition(self._lock)  # signalled on submit and stop
        self._run_lock = threading.Lock()  # held while taking and running a batch: concurrency 1, in queue order
        self._queue: deque[_Request[T, R]] = deque()
        self._thread: threading.Thread | None = None
        self._stopped = False

    def submit(self, job_id: str, item: T) -> Future[R]:
        """Queue one item for `job_id` and return the future its result (or its batch's exception) will be set on."""
        future: Future[R] = Future()
        with self._changed:
            if self._stopped:
                raise RuntimeError(f"{self._name} is stopped and accepts no more requests")
            self._queue.append(_Request(job_id, item, future, self._clock()))
            self._changed.notify()
        return future

    def pending(self) -> int:
        """Requests waiting for a batch."""
        with self._lock:
            return len(self._queue)

    def seconds_until_due(self) -> float | None:
        """Seconds until the next batch is due (0.0 if it is due now), or None when nothing is waiting."""
        with self._lock:
            return self._due_in(self._clock())

    def run_due(self) -> int:
        """Run, in this thread, every batch that is due now. Returns how many batches ran."""
        self._refuse_if_threaded()
        return self._run_while(force=False)

    def flush(self) -> int:
        """Run, in this thread, everything waiting, whether due or not. Returns how many batches ran."""
        self._refuse_if_threaded()
        return self._run_while(force=True)

    def start(self) -> None:
        """Start the background thread that runs batches as they fall due."""
        with self._lock:
            if self._thread is not None:
                raise RuntimeError(f"{self._name} is already started")
            if self._stopped:
                raise RuntimeError(f"{self._name} is stopped")
            self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
            self._thread.start()

    def stop(self, *, drain: bool = True, timeout: float | None = None) -> None:
        """Accept no more requests. With `drain`, run everything waiting first; otherwise cancel it.

        Waits up to `timeout` seconds for the background thread, if started, to finish.
        """
        with self._changed:
            self._stopped = True
            if not drain:
                while self._queue:
                    self._queue.popleft().future.cancel()
            self._changed.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
        else:
            self._run_while(force=True)

    # --- internals ---------------------------------------------------------------------------------------------

    def _refuse_if_threaded(self) -> None:
        if self._thread is not None:
            raise RuntimeError(f"{self._name} runs its own thread; do not drive it by hand")

    def _due_in(self, now: float) -> float | None:
        """Seconds until a batch is due. Call with the lock held."""
        if not self._queue:
            return None
        if len(self._queue) >= self._max_batch_size:
            return 0.0
        return max(0.0, self._queue[0].submitted_at + self._max_wait_s - now)

    def _run_while(self, *, force: bool) -> int:
        count = 0
        while self._run_one(force=force):
            count += 1
        return count

    def _run_one(self, *, force: bool) -> bool:
        """Take one batch if one is due (or any is waiting, with `force`) and run it. False if there was none."""
        with self._run_lock:
            with self._lock:
                due_in = self._due_in(self._clock())
                if due_in is None or (due_in > 0 and not force):
                    return False
                batch: list[_Request[T, R]] = []
                while self._queue and len(batch) < self._max_batch_size:
                    request = self._queue.popleft()
                    if request.future.set_running_or_notify_cancel():  # False: the job cancelled it
                        batch.append(request)
            if batch:
                self._run(batch)
            return True

    def _run(self, batch: list[_Request[T, R]]) -> None:
        items = [request.item for request in batch]
        try:
            results = list(self._process_batch(items))
            if len(results) != len(items):
                raise ValueError(f"process_batch returned {len(results)} results for {len(items)} items")
        except Exception as exc:
            jobs = sorted({request.job_id for request in batch})
            logger.exception("%s: batch of %d items failed (jobs %s)", self._name, len(items), ", ".join(jobs))
            for request in batch:
                request.future.set_exception(exc)
            return
        for request, result in zip(batch, results, strict=True):
            request.future.set_result(result)

    def _loop(self) -> None:
        while True:
            with self._changed:
                while True:
                    due_in = self._due_in(self._clock())
                    if due_in is None:
                        if self._stopped:
                            return
                        self._changed.wait()
                    elif due_in <= 0 or self._stopped:
                        break
                    else:
                        self._changed.wait(timeout=due_in)
                force = self._stopped
            self._run_one(force=force)
