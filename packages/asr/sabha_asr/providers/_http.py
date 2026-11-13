"""What the HTTP providers (OpenAI, Qwen) share: sending one chunk with waits on rate limits, and turning a failed
response into a ProviderError.

Retryable: network errors, timeouts, and HTTP 429/500/502/503/504, except an error code that says waiting will not
help (no credit, bad key). A 429 is sent again after a wait, up to RATE_LIMIT_RETRIES times: the provider's
Retry-After when given (at most MAX_WAIT_S), else 2, 4, 8, 16 s. Each wait is logged. Reasons name the status and the
provider's error code only: never the key, audio or transcript text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from sabha_asr.provider import ProviderError

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
RATE_LIMIT_RETRIES = 4
MAX_WAIT_S = 30.0


def send(
    provider: str,
    request: Callable[[], httpx.Response],
    *,
    not_retryable: frozenset[str],
    sleep: Callable[[float], None],
    log: logging.Logger,
    chunk_id: str,
) -> httpx.Response:
    """The first response that is not a retryable 429, or the last one; raises ProviderError on network errors."""
    response = _call(provider, request)
    for retry in range(1, RATE_LIMIT_RETRIES + 1):
        if response.status_code != 429 or not error_for(provider, response, not_retryable).retryable:
            break
        wait = _retry_after(response) or float(2**retry)
        log.warning("rate limit; waiting before sending the chunk again",
                    extra={"provider": provider, "chunk_id": chunk_id, "wait_s": wait, "retry": retry})  # fmt: skip
        sleep(wait)
        response = _call(provider, request)
    return response


def _call(provider: str, request: Callable[[], httpx.Response]) -> httpx.Response:
    try:
        return request()
    except httpx.TimeoutException as exc:
        raise ProviderError(provider, f"timed out ({type(exc).__name__})", retryable=True) from exc
    except httpx.TransportError as exc:
        raise ProviderError(provider, f"network error ({type(exc).__name__})", retryable=True) from exc


def _retry_after(response: httpx.Response) -> float | None:
    try:
        seconds = float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
    return min(max(seconds, 0.0), MAX_WAIT_S)


def error_for(provider: str, response: httpx.Response, not_retryable: frozenset[str]) -> ProviderError:
    """A failed response as a ProviderError. The code is the provider's `error.code` (or `error.type`, or a top-level
    `code`), so "insufficient_quota" or a bad key is not retried."""
    code = "unknown"
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            found = error.get("code") or error.get("type")
        else:
            found = body.get("code") if isinstance(body, dict) else None
        if isinstance(found, str) and found:
            code = found
    except ValueError:
        pass
    retryable = response.status_code in RETRYABLE_STATUSES and code not in not_retryable
    return ProviderError(provider, f"HTTP {response.status_code} {code}", retryable=retryable)


def json_body(provider: str, response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(provider, "response is not JSON", retryable=False) from exc
