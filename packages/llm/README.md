# packages/llm

`sabha_llm`, the only way any code calls an LLM (plan task P5.1).

```python
gateway = build_gateway(settings, database=db, redis=redis)  # once per worker process
result = gateway.complete(
    task="analysis.scoring", messages=[...], tenant_id=..., recording_id=..., json_schema=schema, prompt_version="3"
)
```

| Step | What happens |
| --- | --- |
| Routing | The task's tier (`tasks.py`) picks the model from `LLM_MODEL_SMALL` / `LLM_MODEL_MID`. Unknown tasks and models fail at start-up. |
| Redaction | Every message goes through `redact.py` before it leaves our servers (golden rule 8). |
| Budgets | Daily token budgets per tenant and overall, in Redis (`budget.py`); unset means no limit. |
| Retries | Only 429, 5xx and timeouts, with exponential backoff and full jitter (`LLM_MAX_RETRIES`). |
| Fallback | Only the models listed for the task in `LLM_FALLBACKS`, each switch logged and recorded (golden rule 7). |
| JSON | Answers are validated against the schema; one repair attempt, then `InvalidJsonError` (or `invalid_json="none"` to let the caller re-ask). |
| Accounting | Every provider call goes to `llm_calls` with tokens, cost and latency; no prompt text, only its hash. |
| Tracing | One OpenTelemetry span per call (task, model, prompt hash and version, tokens, cost). Langfuse is not used until it can be self-hosted in India (golden rule 12). |

Providers: OpenAI through the Responses API (`providers/openai.py`) and a scripted fake for tests. `catalog.py` lists the models with their published prices (only from `docs/llm-providers.md`, with source and date) and the parameters they are documented to accept; cost is `None` for a model without prices (golden rule 6).

`sabha_analytics.judge.GatewayJudge` adapts the gateway to the analytics `JudgeModel` interface.
