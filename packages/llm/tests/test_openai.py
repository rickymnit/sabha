"""The OpenAI Responses adapter against a mocked transport: request shape, parsing, errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sabha_llm.errors import ProviderError
from sabha_llm.providers.openai import OpenAIProvider
from sabha_llm.types import Message, ProviderRequest

Handler = Callable[[httpx.Request], httpx.Response]
REQUEST = ProviderRequest(model="o3-mini", messages=(Message("system", "Score."), Message("user", "Lesson text")))


def provider(handler: Handler) -> OpenAIProvider:
    return OpenAIProvider("sk-test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def answer(text: str = '{"score": 4}', **extra: Any) -> dict[str, Any]:
    return {
        "model": "o3-mini-2025-01-31",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 1200, "input_tokens_details": {"cached_tokens": 1024}, "output_tokens": 300},
        **extra,
    }


def test_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer())

    schema = {"type": "object"}
    provider(handler).complete(
        ProviderRequest(model="o3-mini", messages=REQUEST.messages, json_schema=schema, max_tokens=2000)
    )
    (request,) = seen
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = httpx.Response(200, content=request.content).json()
    assert body == {
        "model": "o3-mini",
        "input": [{"role": "system", "content": "Score."}, {"role": "user", "content": "Lesson text"}],
        "max_output_tokens": 2000,
        "text": {"format": {"type": "json_schema", "name": "answer", "schema": schema, "strict": True}},
    }  # no temperature or reasoning effort unless the catalog says the model takes them


def test_optional_parameters_are_sent_only_when_given() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(httpx.Response(200, content=request.content).json())
        return httpx.Response(200, json=answer())

    provider(handler).complete(
        ProviderRequest(model="x", messages=REQUEST.messages, temperature=0.0, reasoning_effort="low")
    )
    assert seen[0]["temperature"] == 0.0 and seen[0]["reasoning"] == {"effort": "low"}


def test_text_and_usage_are_read_from_the_response() -> None:
    result = provider(lambda r: httpx.Response(200, json=answer())).complete(REQUEST)
    assert result.text == '{"score": 4}'
    assert (result.usage.tokens_in, result.usage.cached_tokens, result.usage.tokens_out) == (1200, 1024, 300)
    assert result.model_id == "o3-mini-2025-01-31"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (answer(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "incomplete"),
        ({**answer(), "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}, "refused"),
        ({**answer(), "output": []}, "no output text"),
    ],
)
def test_unusable_answers_are_not_retried(body: dict[str, Any], reason: str) -> None:
    with pytest.raises(ProviderError, match=reason) as raised:
        provider(lambda r: httpx.Response(200, json=body)).complete(REQUEST)
    assert raised.value.retryable is False


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "rate_limit_exceeded", True),
        (429, "insufficient_quota", False),
        (500, "server_error", True),
        (503, "overloaded", True),
        (400, "invalid_request_error", False),
        (401, "invalid_api_key", False),
    ],
)
def test_http_errors(status: int, code: str, retryable: bool) -> None:
    body = {"error": {"message": "details that may echo the prompt", "code": code}}
    with pytest.raises(ProviderError) as raised:
        provider(lambda r: httpx.Response(status, json=body)).complete(REQUEST)
    assert raised.value.retryable is retryable
    assert raised.value.reason == f"HTTP {status} {code}" and "prompt" not in str(raised.value)


def test_timeouts_are_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderError) as raised:
        provider(handler).complete(REQUEST)
    assert raised.value.retryable is True
