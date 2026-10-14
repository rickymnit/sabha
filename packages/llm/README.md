# packages/llm

`sabha_llm`, the gateway for every LLM call: provider adapters, routing, budgets, retries, prompt caching, cost accounting and Langfuse tracing. It masks PII (phone, Aadhaar-like and PAN-like numbers, emails) before any text leaves our servers, and provider fallbacks happen only when configured and are logged.
