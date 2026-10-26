"""OpenAI through the Responses API, which OpenAI recommends for its reasoning models (gpt-6-luna; formerly o3-mini).

Request: POST {base_url}/responses with `model`, `input` (messages, system role included), `max_output_tokens`, and
for JSON answers `text.format = {type: "json_schema", name, schema, strict: true}` (structured outputs). Optional
`temperature` / `reasoning.effort` are sent only when the gateway passes them, which it does only for models the
catalog marks as accepting them.

Response: the text of every `output_text` part of the `message` items. A refusal, or `status: "incomplete"`
(for example cut off at max_output_tokens), is a non-retryable ProviderError. Usage: `input_tokens`,
`input_tokens_details.cached_tokens` and `.cache_write_tokens` (both parts of `input_tokens`; checked 2026-10-26),
`output_tokens` (reasoning tokens are part of output tokens).

Errors: 429, 5xx and timeouts are retryable; other statuses are not. Reasons carry the status and OpenAI's error
code only, never prompt or answer text.
"""

from __future__ import annotations

from typing import Any

import httpx

from sabha_llm.errors import ProviderError
from sabha_llm.types import ProviderRequest, ProviderResponse, Usage

NAME = "openai"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    name = NAME

    def __init__(
        self, api_key: str, *, base_url: str | None = None, timeout_s: float = 120.0, client: httpx.Client | None = None
    ) -> None:
        if not api_key:
            raise ValueError("an OpenAI API key is required")
        self._url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/responses"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=timeout_s, follow_redirects=False)

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        body: dict[str, Any] = {
            "model": request.model,
            "input": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.max_tokens is not None:
            body["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.reasoning_effort is not None:
            body["reasoning"] = {"effort": request.reasoning_effort}
        if request.json_schema is not None:
            body["text"] = {
                "format": {"type": "json_schema", "name": "answer", "schema": request.json_schema, "strict": True}
            }
        try:
            response = self._client.post(self._url, headers=self._headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(NAME, f"timed out ({type(exc).__name__})", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ProviderError(NAME, f"network error ({type(exc).__name__})", retryable=True) from exc
        if response.status_code != 200:
            raise _http_error(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(NAME, "response is not JSON", retryable=False, status=200) from exc
        return _parse(data)


def _http_error(response: httpx.Response) -> ProviderError:
    code = "unknown"
    try:
        error = response.json().get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or "unknown")
    except (ValueError, AttributeError):
        pass
    status = response.status_code
    retryable = status == 429 or status >= 500
    if code == "insufficient_quota":
        retryable = False  # billing, not load: retrying cannot help
    return ProviderError(NAME, f"HTTP {status} {code}", retryable=retryable, status=status)


def _parse(data: Any) -> ProviderResponse:
    if not isinstance(data, dict):
        raise ProviderError(NAME, "response is not an object", retryable=False)
    if data.get("status") == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason", "unknown")
        raise ProviderError(NAME, f"incomplete answer ({reason})", retryable=False)
    texts, refused = [], False
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue  # reasoning summaries and other items
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif isinstance(part, dict) and part.get("type") == "refusal":
                refused = True
    if refused:
        raise ProviderError(NAME, "the model refused", retryable=False)
    if not texts:
        raise ProviderError(NAME, "response has no output text", retryable=False)
    usage = data.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    cached, written = details.get("cached_tokens") or 0, details.get("cache_write_tokens") or 0
    return ProviderResponse(
        text="".join(texts),
        usage=Usage(
            int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), int(cached), int(written)
        ),
        model_id=str(data.get("model") or "unknown"),
    )
