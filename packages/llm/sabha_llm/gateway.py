"""The LLM gateway: the only way any code calls an LLM (plan task P5.1; golden rules 5, 7 and 8).

`Gateway.complete(task=..., messages=..., tenant_id=...)`:

1. Routing: the task's tier (sabha_llm.tasks) picks the model from settings; an unknown task is a config error.
2. Redaction: every message is passed through sabha_llm.redact before it leaves our servers (golden rule 8). Callers
   that know student names redact first with those names (to keep the mapping for grounding); running the
   patterns again is harmless.
3. Budget: today's tenant and global token budgets are checked (sabha_llm.budget).
4. Call with retries: only retryable errors (429, 5xx, timeouts) are retried, up to LLM_MAX_RETRIES times with
   exponential backoff and full jitter. Other errors go straight to the next model.
5. Fallback: the task's LLM_FALLBACKS models, in order, only when configured; every switch is logged with the reason
   and recorded on the result and in llm_calls (golden rule 7). If every model fails, the last error is raised.
6. JSON: with a schema, the answer must parse and validate. `invalid_json="repair"` (default) asks once more with
   the validation error, then raises InvalidJsonError; `invalid_json="none"` returns json=None and lets the caller
   decide (sabha_analytics re-asks itself).
7. Accounting: every provider call, failed or not, is written to llm_calls with tokens, cost from the published
   price table (None if the model has none) and latency; tokens are charged to the budgets; and the whole call is
   an OpenTelemetry span with task, model, prompt hash and version, tokens and cost (no prompt text).
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from opentelemetry import trace

from sabha_core.models import LlmCall
from sabha_llm.budget import TokenBudget
from sabha_llm.catalog import ModelSpec, cost_usd, spec_for
from sabha_llm.errors import InvalidJsonError, LlmConfigError, ProviderError
from sabha_llm.redact import redact
from sabha_llm.tasks import TASK_TIERS
from sabha_llm.types import CompletionResult, Message, ProviderRequest, ProviderResponse, Tier, Usage
from sabha_llm.usage import UsageSink

log = logging.getLogger("sabha.llm")
tracer = trace.get_tracer("sabha.llm")

_BACKOFF_BASE_S = 1.0
_BACKOFF_CAP_S = 30.0
_REPAIR = (
    "Your previous answer did not match the required JSON schema ({error}). Reply again with only JSON that "
    "matches the schema exactly."
)


class Provider(Protocol):
    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


def prompt_hash(messages: Sequence[Message], json_schema: Mapping[str, Any] | None) -> str:
    canonical = json.dumps(
        {"messages": [[m.role, m.content] for m in messages], "schema": json_schema},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class Gateway:
    def __init__(
        self,
        *,
        providers: Mapping[str, Provider],
        models: Mapping[Tier, str],
        fallbacks: Mapping[str, Sequence[str]] | None = None,
        max_retries: int = 3,
        budget: TokenBudget,
        usage: UsageSink,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._providers = dict(providers)
        self._models = dict(models)
        self._fallbacks = {task: list(chain) for task, chain in (fallbacks or {}).items()}
        self._max_retries = max_retries
        self._budget = budget
        self._usage = usage
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        unknown = sorted(set(self._fallbacks) - set(TASK_TIERS))
        if unknown:
            raise LlmConfigError(f"LLM_FALLBACKS names unknown tasks: {unknown}")
        for key in [*self._models.values(), *(m for chain in self._fallbacks.values() for m in chain)]:
            self._spec(key)  # fails at start-up, not on the first call

    def _spec(self, key: str) -> ModelSpec:
        spec = spec_for(key)
        if spec.provider not in self._providers:
            raise LlmConfigError(f"model {key!r} needs the {spec.provider!r} provider, which is not configured")
        return spec

    def complete(
        self,
        *,
        task: str,
        messages: Sequence[Message],
        tenant_id: str,
        recording_id: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        prompt_version: str | None = None,
        invalid_json: Literal["repair", "none"] = "repair",
    ) -> CompletionResult:
        tier = TASK_TIERS.get(task)
        if tier is None:
            raise LlmConfigError(f"unknown LLM task {task!r}; add it to sabha_llm.tasks.TASK_TIERS")
        chain = [self._models[tier], *self._fallbacks.get(task, [])]
        safe = tuple(Message(m.role, redact(m.content).redacted_text) for m in messages)
        digest = prompt_hash(safe, json_schema)
        context = {"task": task, "tenant_id": tenant_id, "recording_id": recording_id, "prompt_hash": digest,
                   "prompt_version": prompt_version}  # fmt: skip

        with tracer.start_as_current_span("llm.complete") as span:
            span.set_attributes({"llm.task": task, "llm.prompt_hash": digest, "sabha.tenant_id": tenant_id})
            if prompt_version:
                span.set_attribute("llm.prompt_version", prompt_version)
            if recording_id:
                span.set_attribute("sabha.recording_id", recording_id)
            self._budget.check(tenant_id)

            failures: list[str] = []
            for key in chain:
                spec = self._spec(key)
                if failures:
                    log.warning(
                        "LLM call failed; using the configured fallback",
                        extra={"task": task, "fallback_model": key, "reason": failures[-1]},
                    )
                fallback_reason = "; ".join(failures) or None
                request = ProviderRequest(
                    model=spec.name, messages=safe, json_schema=json_schema, max_tokens=max_tokens
                )
                try:
                    response, latency_ms, usage = self._call(spec, request, context, fallback_reason)
                except ProviderError as exc:
                    failures.append(f"{key}: {exc.reason}")
                    continue
                parsed: Any = None
                if json_schema is not None:
                    parsed, problem = _parse(response.text, json_schema)
                    if problem is not None and invalid_json == "repair":
                        self._budget.check(tenant_id)
                        repair = ProviderRequest(
                            model=spec.name,
                            messages=(
                                *safe,
                                Message("assistant", response.text),
                                Message("user", _REPAIR.format(error=problem)),
                            ),
                            json_schema=json_schema,
                            max_tokens=max_tokens,
                        )
                        response, extra_ms, extra = self._call(spec, repair, context, fallback_reason)
                        latency_ms, usage = (
                            latency_ms + extra_ms,
                            Usage(
                                usage.tokens_in + extra.tokens_in,
                                usage.tokens_out + extra.tokens_out,
                                usage.cached_tokens + extra.cached_tokens,
                            ),
                        )
                        parsed, problem = _parse(response.text, json_schema)
                        if problem is not None:
                            raise InvalidJsonError(f"{key} answered {task} with invalid JSON twice: {problem}")
                    elif problem is not None:
                        parsed = None
                cost = cost_usd(spec, usage.tokens_in, usage.cached_tokens, usage.tokens_out)
                span.set_attributes(
                    {
                        "llm.model": key,
                        "llm.tokens_in": usage.tokens_in,
                        "llm.tokens_out": usage.tokens_out,
                        "llm.cached_tokens": usage.cached_tokens,
                        "llm.failed_attempts": len(failures),
                    }
                )
                if cost is not None:
                    span.set_attribute("llm.cost_usd", cost)
                return CompletionResult(
                    task=task,
                    model=key,
                    text=response.text,
                    json=parsed,
                    usage=usage,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    prompt_hash=digest,
                    fallback_reason=fallback_reason,
                    attempts=failures,
                )
            span.set_attribute("llm.failed_attempts", len(failures))
            raise ProviderError("gateway", f"every model failed for {task}: {'; '.join(failures)}", retryable=False)

    def _call(
        self, spec: ModelSpec, request: ProviderRequest, context: Mapping[str, Any], fallback_reason: str | None
    ) -> tuple[ProviderResponse, int, Usage]:
        """One logical call with retries on retryable errors; every provider attempt is recorded."""
        provider = self._providers[spec.provider]
        for attempt in range(1, self._max_retries + 2):
            started = self._clock()
            try:
                response = provider.complete(request)
            except ProviderError as exc:
                self._record(spec, context, attempt, started, Usage(), fallback_reason, error=exc)
                if not exc.retryable or attempt > self._max_retries:
                    raise
                self._sleep(self._jitter() * min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * 2 ** (attempt - 1)))
                continue
            latency_ms = self._record(spec, context, attempt, started, response.usage, fallback_reason)
            self._budget.charge(str(context["tenant_id"]), response.usage.total)
            return response, latency_ms, response.usage
        raise AssertionError("unreachable")  # pragma: no cover

    def _record(
        self,
        spec: ModelSpec,
        context: Mapping[str, Any],
        attempt: int,
        started: float,
        usage: Usage,
        fallback_reason: str | None,
        error: ProviderError | None = None,
    ) -> int:
        latency_ms = max(0, round((self._clock() - started) * 1000))
        self._usage.record(
            LlmCall(
                tenant_id=str(context["tenant_id"]),
                recording_id=context["recording_id"],
                task=str(context["task"]),
                provider=spec.provider,
                model=spec.name,
                prompt_hash=str(context["prompt_hash"]),
                prompt_version=context["prompt_version"],
                status="error" if error else "ok",
                error_code=error.reason if error else None,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
                cached_tokens=usage.cached_tokens,
                cost_usd=cost_usd(spec, usage.tokens_in, usage.cached_tokens, usage.tokens_out),
                latency_ms=latency_ms,
                attempt=attempt,
                fallback_reason=fallback_reason,
            )
        )
        return latency_ms


def _parse(text: str, schema: Mapping[str, Any]) -> tuple[Any, str | None]:
    """(parsed JSON, None) if `text` is JSON valid for `schema`; (None, problem) otherwise."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"not JSON: {exc.msg} at character {exc.pos}"
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        return None, f"{path}: {exc.message}"[:300]
    return data, None
