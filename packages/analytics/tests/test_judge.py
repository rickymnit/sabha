"""GatewayJudge: sabha_analytics' JudgeModel on top of the LLM gateway (plan task P5.1)."""

from __future__ import annotations

from typing import Any

import pytest

from sabha_analytics.judge import GatewayJudge
from sabha_analytics.scoring import TASK_SCORING, TokenUsage
from sabha_llm.budget import TokenBudget
from sabha_llm.gateway import Gateway
from sabha_llm.providers.fake import FakeProvider
from sabha_llm.usage import MemoryUsage

SCHEMA: dict[str, Any] = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}


def judge(answers: list[str]) -> tuple[GatewayJudge, FakeProvider, MemoryUsage]:
    provider, usage = FakeProvider(answers), MemoryUsage()
    gateway = Gateway(
        providers={"fake": provider},
        models={"small": "fake:fake-small", "mid": "fake:fake-mid"},
        budget=TokenBudget(None, tenant_daily=None, global_daily=None),
        usage=usage,
    )
    return GatewayJudge(gateway, tenant_id="tenant-a", recording_id="rec-1", prompt_version="3"), provider, usage


def test_complete_json_maps_to_the_gateway() -> None:
    model, provider, usage = judge(['{"score": 4}'])
    response = model.complete_json(
        task=TASK_SCORING,
        system="Score the lesson.",
        messages=[{"role": "user", "content": "transcript"}],
        json_schema=SCHEMA,
        cache_prefix="transcript",
    )
    assert response.data == {"score": 4} and response.model_id == "fake:fake-mid"
    assert response.usage == TokenUsage(input_tokens=100, output_tokens=20)
    assert [m.role for m in provider.requests[0].messages] == ["system", "user"]
    (call,) = usage.calls
    assert (call.tenant_id, call.recording_id, call.prompt_version) == ("tenant-a", "rec-1", "3")


def test_invalid_json_comes_back_as_none_for_scoring_to_re_ask() -> None:
    model, provider, _ = judge(["not json"])
    response = model.complete_json(
        task=TASK_SCORING,
        system="s",
        messages=[{"role": "user", "content": "t"}],
        json_schema=SCHEMA,
        cache_prefix=None,
    )
    assert response.data is None and len(provider.requests) == 1


def test_unknown_roles_are_refused() -> None:
    model, _, _ = judge(["{}"])
    with pytest.raises(ValueError, match="role"):
        model.complete_json(
            task=TASK_SCORING,
            system="s",
            messages=[{"role": "tool", "content": "t"}],
            json_schema=SCHEMA,
            cache_prefix=None,
        )


def test_a_redacted_transcript_and_the_real_prompts_go_through_the_real_gateway(lesson: Any, rubric: Any,
                                                                                  answers: Any) -> None:  # fmt: skip
    # Found in the first end-to-end run: the gateway's own redaction refused text that was already redacted (the
    # transcript's [STUDENT_1]) and prompts that explain placeholders. Only the provider is fake here.
    import json

    from sabha_analytics.report import analyse

    synthesis = {
        "summary": "A clear lesson on photosynthesis with a short recap at the end.",
        "strengths": ["Defines key terms in plain words.", "Links ideas to everyday experience."],
        "gaps": ["Few checks that students understood.", "The recap is brief."],
        "suggestions": [
            {"text": "Ask a student to explain photosynthesis back in their own words.", "utterance_id": "u0001"},
            {"text": "Pause after defining chlorophyll and ask why leaves are green.", "utterance_id": "u0003"},
            {"text": "Let students state the two key ideas in the recap.", "utterance_id": "u0004"},
        ],
    }
    model, provider, _ = judge([json.dumps({"dimensions": [answers.good_concept, answers.good_recap]}),
                                json.dumps(synthesis)])  # fmt: skip
    metrics = [{"key": "teacher_talk_share", "value": 0.82, "unit": "ratio", "definition": "Teacher talk share."}]
    result = analyse(rubric=rubric, transcript=lesson, metrics=metrics, model=model, analysed_roles={"teacher"})
    assert result.report["overall"]["score"] == 3.6
    sent = " ".join(m.content for request in provider.requests for m in request.messages)
    assert "[STUDENT_1]" in sent  # the caller's placeholder, unchanged, so grounding can still map it
    assert "Aman" not in sent and "9876543210" not in sent
