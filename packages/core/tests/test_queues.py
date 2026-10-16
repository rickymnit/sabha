"""Short recordings take the priority lane on gpu.speech and llm.analyze only."""

from __future__ import annotations

from sabha_core.queues import CPU_PREPROCESS, GPU_SPEECH, IO_NOTIFY, LLM_ANALYZE, all_queues, queue_for


def test_short_recordings_use_the_priority_variant() -> None:
    assert queue_for(GPU_SPEECH, 599.9) == "gpu.speech.priority"
    assert queue_for(LLM_ANALYZE, 120) == "llm.analyze.priority"


def test_ten_minutes_or_more_use_the_normal_queue() -> None:
    assert queue_for(GPU_SPEECH, 600) == GPU_SPEECH
    assert queue_for(LLM_ANALYZE, 3600) == LLM_ANALYZE


def test_other_queues_have_no_lane() -> None:
    assert queue_for(CPU_PREPROCESS, 30) == CPU_PREPROCESS
    assert queue_for(IO_NOTIFY, 30) == IO_NOTIFY


def test_every_queue_a_task_can_reach_is_listed() -> None:
    queues = set(all_queues())
    for base in (CPU_PREPROCESS, GPU_SPEECH, LLM_ANALYZE, IO_NOTIFY):
        for duration in (30, 3600):
            assert queue_for(base, duration) in queues
