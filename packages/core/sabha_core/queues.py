"""Celery queue names and the priority lane (CLAUDE.md queues; plan task P7.2).

Recordings shorter than SHORT_RECORDING_S go to the `.priority` variant of gpu.speech and llm.analyze, which
workers consume first, so a short call is not stuck behind a school's bulk upload of hour-long lessons. Inside
gpu.speech the fair scheduler (sabha_workers.fair_scheduler, ADR 0005) shares GPU time between tenants.
"""

from __future__ import annotations

from typing import Final

CPU_PREPROCESS: Final = "cpu.preprocess"
GPU_SPEECH: Final = "gpu.speech"
LLM_ANALYZE: Final = "llm.analyze"
IO_NOTIFY: Final = "io.notify"
BILLING_METER: Final = "billing.meter"

PRIORITY_SUFFIX: Final = ".priority"
SHORT_RECORDING_S: Final = 600.0
"""Under 10 minutes counts as short (P7.2); the same threshold as the fair scheduler's short lane."""

_LANED = frozenset({GPU_SPEECH, LLM_ANALYZE})


def queue_for(base: str, duration_s: float) -> str:
    """The queue a recording's task goes to: the priority variant for short recordings on laned queues."""
    if base in _LANED and duration_s < SHORT_RECORDING_S:
        return base + PRIORITY_SUFFIX
    return base


def all_queues() -> tuple[str, ...]:
    """Every queue workers may consume, priority variants included."""
    base = (CPU_PREPROCESS, GPU_SPEECH, LLM_ANALYZE, IO_NOTIFY, BILLING_METER)
    return base + tuple(sorted(q + PRIORITY_SUFFIX for q in _LANED))
