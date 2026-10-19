"""`JudgeModel` (sabha_analytics.scoring) on top of the LLM gateway (sabha_llm.gateway, plan task P5.1).

The analyze stage builds one `GatewayJudge` per recording, so every call is accounted to the right tenant and
recording. Invalid JSON is returned as `data=None` (`invalid_json="none"`): scoring and synthesis re-ask once
themselves, with their own prompt. `cache_prefix` needs no request flag: OpenAI caches long stable prefixes
automatically, and the callers already put the stable part (system prompt, rubric, transcript) first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sabha_analytics.scoring import JudgeResponse, TokenUsage
from sabha_llm.gateway import Gateway
from sabha_llm.types import Message


class GatewayJudge:
    def __init__(
        self, gateway: Gateway, *, tenant_id: str, recording_id: str, prompt_version: str | None = None
    ) -> None:
        self._gateway = gateway
        self._tenant_id = tenant_id
        self._recording_id = recording_id
        self._prompt_version = prompt_version

    def complete_json(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        json_schema: Mapping[str, Any],
        cache_prefix: str | None,
    ) -> JudgeResponse:
        conversation = [Message("system", system)]
        for message in messages:
            if message["role"] == "user":
                conversation.append(Message("user", message["content"]))
            elif message["role"] == "assistant":
                conversation.append(Message("assistant", message["content"]))
            else:
                raise ValueError(f"unexpected message role {message['role']!r}")
        result = self._gateway.complete(
            task=task,
            messages=conversation,
            tenant_id=self._tenant_id,
            recording_id=self._recording_id,
            json_schema=dict(json_schema),
            prompt_version=self._prompt_version,
            invalid_json="none",
        )
        return JudgeResponse(
            data=result.json,
            model_id=result.model,
            usage=TokenUsage(
                input_tokens=result.usage.tokens_in,
                output_tokens=result.usage.tokens_out,
                cache_read_tokens=result.usage.cached_tokens,
            ),
        )
