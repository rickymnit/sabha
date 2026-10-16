"""Fair scheduling of GPU work across tenants (plan task P7.2; design in docs/adr/0005-fairness.md).

The unit of work is a CHUNK of a recording (about 30 s of compact audio, P3.5), never a whole recording: if a
three-hour lesson held the GPU as one job, a short call from another school would wait for all of it, however
the queue was ordered. Scheduling chunks bounds that wait to a few chunks.

Two lanes:

- short: chunks of recordings under SHORT_RECORDING_S (10 minutes), e.g. front-desk calls;
- normal: everything else.

The short lane goes first, but after `short_burst` consecutive short picks the normal lane gets one turn if it has
work, so long lessons are never starved.

Within a lane, weighted deficit round robin (DRR) across tenants: tenants with work take turns; on its turn a
tenant's deficit grows by `quantum_s * weight`, and it sends chunks from the front of its queue while their cost
fits in the deficit. Over time each backlogged tenant receives GPU time in proportion to its weight (from its
plan), whatever its backlog size, and one tenant's thousand chunks cannot push another tenant's chunk back by more
than one round. A tenant whose queue empties leaves the round and its deficit resets, so idle tenants cannot save
up credit. Chunks of one tenant keep their submission order.

This class is pure and single-threaded; the gpu.speech dispatcher (P2.4) owns one instance and its persistence.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

SHORT_RECORDING_S = 600.0
DEFAULT_QUANTUM_S = 30.0
DEFAULT_SHORT_BURST = 3

Lane = Literal["short", "normal"]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    tenant_id: str
    recording_id: str
    cost_s: float
    """Expected GPU cost; audio seconds of the chunk are a good proxy."""
    recording_duration_s: float
    """Length of the whole recording: decides the lane."""


@dataclass
class _Lane:
    queues: OrderedDict[str, deque[Chunk]] = field(default_factory=OrderedDict)
    deficits: dict[str, float] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return any(self.queues.values())


class FairScheduler:
    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
        quantum_s: float = DEFAULT_QUANTUM_S,
        short_burst: int = DEFAULT_SHORT_BURST,
        short_threshold_s: float = SHORT_RECORDING_S,
    ) -> None:
        if any(w <= 0 for w in (weights or {}).values()):
            raise ValueError("tenant weights must be positive")
        if quantum_s <= 0 or short_burst < 1:
            raise ValueError("quantum must be positive and short_burst at least 1")
        self._weights = dict(weights or {})
        self._quantum = quantum_s
        self._short_burst = short_burst
        self._short_threshold = short_threshold_s
        self._lanes: dict[Lane, _Lane] = {"short": _Lane(), "normal": _Lane()}
        self._short_streak = 0

    def submit(self, chunk: Chunk) -> None:
        lane = self._lanes["short" if chunk.recording_duration_s < self._short_threshold else "normal"]
        if chunk.tenant_id not in lane.queues:
            lane.queues[chunk.tenant_id] = deque()
            lane.deficits[chunk.tenant_id] = 0.0
        lane.queues[chunk.tenant_id].append(chunk)

    def next(self) -> Chunk | None:
        """The chunk the GPU should process next, or None when nothing is waiting."""
        short, normal = self._lanes["short"], self._lanes["normal"]
        if short and not (normal and self._short_streak >= self._short_burst):
            self._short_streak += 1
            return self._pick(short)
        if normal:
            self._short_streak = 0
            return self._pick(normal)
        return None

    def _pick(self, lane: _Lane) -> Chunk:
        while True:
            tenant, queue = next(iter(lane.queues.items()))
            if not queue:
                del lane.queues[tenant], lane.deficits[tenant]
                continue
            head = queue[0]
            if lane.deficits[tenant] < head.cost_s:
                # Turn over: add this round's credit and move the tenant to the back of the round.
                lane.deficits[tenant] += self._quantum * self._weights.get(tenant, 1.0)
                if lane.deficits[tenant] < head.cost_s:
                    lane.queues.move_to_end(tenant)
                    continue
            queue.popleft()
            lane.deficits[tenant] -= head.cost_s
            if not queue:
                del lane.queues[tenant], lane.deficits[tenant]
            elif lane.deficits[tenant] < queue[0].cost_s:
                lane.queues.move_to_end(tenant)
            return head


def estimate_completion_s(*, backlog_audio_s: float, recording_audio_s: float, audio_s_per_wall_s: float) -> float:
    """Seconds until a newly uploaded recording is processed: the queued audio ahead of it plus its own audio,
    divided by the MEASURED GPU throughput (audio seconds processed per wall-clock second). A conservative upper
    estimate for the normal lane; the short lane is usually faster. Never invent the throughput: pass the measured
    rolling value from stage_runs."""
    if audio_s_per_wall_s <= 0:
        raise ValueError("throughput must be a positive measured value")
    return (backlog_audio_s + recording_audio_s) / audio_s_per_wall_s
