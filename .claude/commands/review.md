Review the current uncommitted diff (run `git diff` and `git diff --staged`) against CLAUDE.md.

Check, and report each as PASS / FAIL with file:line evidence:
1. Tenant isolation: every MongoDB access goes through the tenant-scoped repo; no raw collection calls in routers, services or tasks.
2. Idempotency: new Celery tasks check for their output artefact first and use acks_late.
3. Timestamps shown to users are on the original timeline (segment map applied).
4. No numbers computed by an LLM; no fabricated metrics in code, tests, docs or UI.
5. No silent provider fallback; fallbacks are explicit and logged.
6. PII redaction happens before any text reaches an LLM provider.
7. Errors use problem+json with a stable code; create endpoints honour Idempotency-Key.
8. Secrets only via settings/env; nothing sensitive logged.
9. Tests exist for new logic and would fail without the change.
10. UI strings use the tenant label dictionary, not hard-coded "Teacher"/"Lesson".

Then list concrete fixes in priority order. Do not edit files unless I say "apply fixes". Focus: $ARGUMENTS
