# Sabha — Conversation Intelligence Platform

Sabha turns recorded conversations (lessons, counselling sessions, front-desk calls, meetings, sales calls)
into speaker-labelled transcripts and rubric-based, evidence-backed feedback. One multi-tenant product
serves schools, colleges and companies; an organisation profile changes labels, default rubrics and rules,
never code. The pilot (8 weeks) covers **teaching and reception for schools**.

Read this file fully before any task. If a request conflicts with a rule below, stop and say so.

## Golden rules (never break these)

1. **Tenant isolation.** Every MongoDB document carries `tenant_id`. All data access goes through the
   tenant-scoped repository in `packages/core/sabha_core/repo.py`. A query without `tenant_id` must raise.
   Never call a raw collection from routers, services or tasks.
2. **The API never touches audio bytes.** Clients upload directly to object storage with presigned multipart
   URLs. The API only authorises, records intent and returns quickly.
3. **Every pipeline stage is idempotent.** A task first checks whether its output artefact exists at
   `{tenant_id}/{recording_id}/{stage}@{version}/` and exits early if so. Celery tasks use `acks_late=True`.
4. **Silence is indexed, not deleted.** VAD produces a segment map from compact audio back to original time.
   Every timestamp shown to a user is on the ORIGINAL recording timeline.
5. **No ungrounded claims.** Numbers (talk share, question counts, pace, silence, monologue length) are computed
   in code. The LLM only judges. Every LLM judgement must cite quotes with timestamps, and the grounding
   verifier must confirm each quote exists in the transcript (normalised fuzzy ratio >= 0.90). Unverified
   output is never shown to users.
6. **No fabricated metrics.** Never invent WER, kappa, accuracy or cost figures in code, docs, tests or UI.
   Quality numbers come only from eval scripts run on real human-annotated data.
7. **No silent fallback.** ASR and LLM provider fallbacks happen only when explicitly configured, and are
   logged with the reason. Never swap a provider quietly on error.
8. **PII redaction before every LLM call.** Phone numbers, Aadhaar-like and PAN-like numbers and emails are
   masked by `packages/llm` before text leaves our servers.
9. **Consent first.** A recording without `consent_ref` cannot move past `UPLOADED`.
10. **Staff are analysed, not students.** No student-level scores, profiles or identification.
11. **Secrets only from environment variables** (see `.env.example`). Never commit secrets or real data.
12. **Data stays in India.** Configure AWS `ap-south-1` and Atlas Mumbai. Do not add services outside India
    without asking.

## Stack

| Area | Choice |
| --- | --- |
| Python | 3.12, `uv` workspaces, `ruff`, `mypy --strict` on `packages/` |
| API | FastAPI, Pydantic v2, Uvicorn; async MongoDB via `pymongo.AsyncMongoClient` (PyMongo 4.9+, not Motor) |
| Workers | Celery 5 on Redis 7; sync `pymongo.MongoClient` inside tasks |
| Database | MongoDB 7 replica set (transactions + change streams required, also in tests) |
| Storage | S3 (`ap-south-1`) in staging/prod, RustFS locally (see `docs/adr/0003-local-object-storage.md`); boto3 |
| Audio | ffmpeg/ffprobe, Silero VAD, pyannote or NeMo Sortformer, ASR via `packages/asr` |
| LLM | `packages/llm` gateway (routing, budgets, retries, caching), Langfuse tracing, Presidio redaction |
| Web | React 18 + TypeScript + Vite, Tailwind, TanStack Query, React Router, Vitest, Playwright |
| Auth | OIDC with Auth0 (`docs/adr/0002-auth.md`); JWT validated in the API; roles and tenants from our own records |
| Infra | Docker Compose (dev, staging, prod pilot), Terraform for AWS, GitHub Actions |
| Observability | OpenTelemetry, Prometheus, Grafana, Sentry, structured JSON logs |

## Repo layout

```
apps/api/            FastAPI app: routers/, services/, schemas/, auth/, main.py
apps/workers/        Celery app and tasks: preprocess.py, speech.py, analyze.py, notify.py, meter.py, relay.py
apps/web/            React app; src/design/ holds tokens and components
packages/core/       sabha_core: settings, repo (tenant-scoped), models, state machine, storage, logging, telemetry
packages/asr/        sabha_asr: multi-provider ASR abstraction (built here; there is no earlier codebase to port)
packages/llm/        sabha_llm: gateway, providers, redaction, prompt caching, cost accounting
packages/analytics/  sabha_analytics: rubric loader, metrics, scoring, grounding, synthesis
rubrics/             rubric files: <type>.<segment>.v<major>.<minor>.yaml
eval/                gold-set manifests, wer.py, roles.py, kappa.py, grounding.py, bakeoff.py, reports/
infra/               docker-compose.*.yml, terraform/, loadtest/, grafana/
docs/                adr/, runbook.md, prompts/, design/, guides for raters and schools
```

## Domain model

Collections: `tenants, units, users, people, recordings, stage_runs, transcripts, rubrics, analyses, scores,
disputes, usage_events, outbox, audit_log`, plus `identities` (login links, ADR 0002), `idempotency_keys`
(create replays, 24 h TTL), `llm_calls` (LLM usage, P5.1), `dlq` (failed pipeline jobs, P2.4) and `relay_state`. The full list with indexes is `sabha_core/indexes.py`.

Recording status (state machine in `sabha_core/state.py`, the ONLY place transitions are defined):
`CREATED → UPLOADED → PREPROCESSING → DIARIZING → TRANSCRIBING → ANALYZING → COMPLETED`,
plus `FAILED` and `NEEDS_REVIEW` reachable from any worker stage.

Queues: `cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`.

Organisation profiles: `school` (pilot), `college`, `company`. UI words come from the tenant's `labels`
dictionary (`person`, `recording`, `unit`, ...). Never hard-code "Teacher" or "Lesson" in UI strings.

## API conventions

- Versioned paths `/v1/...`; OpenAPI must stay accurate.
- `Idempotency-Key` header on every create; replays return the original response.
- Errors: RFC 9457 `application/problem+json` with a stable `code` and `request_id`.
- Cursor pagination (`?cursor=&limit=`), never offset.
- Times stored in UTC (ISO 8601); the web app displays Asia/Kolkata.
- Every playback, export and score change writes `audit_log`.

## Commands

```
make dev          # docker compose up: mongo (replica set), redis, rustfs, api, workers, web
make test         # all Python tests (testcontainers) + web unit tests
make lint         # ruff, mypy, eslint, tsc
make e2e          # Playwright against the dev stack
make eval-wer     # eval/wer.py on the frozen gold set
make eval-kappa   # eval/kappa.py on the calibration hold-out split
```

## How to work in this repo

- **Plan first.** For any task bigger than a small fix, propose a plan (files, functions, tests) and wait for
  approval before writing code.
- **Small diffs.** One concern per change. Keep each PR reviewable in under 15 minutes.
- **Tests with every change.** Unit tests for logic; integration tests with testcontainers for anything touching
  MongoDB, Redis or storage. Critical paths (tenant isolation, grounding, idempotency, state machine) need
  tests written before the implementation.
- **No new dependencies without saying why** and noting it in the PR description.
- **Record decisions** that change architecture as an ADR in `docs/adr/NNNN-title.md`.
- **Never** weaken a test to make it pass, mock away the tenant check, or add `# type: ignore` without a reason.
- **When unsure** about a product rule, ask rather than guess.

## Definition of done

Merged to main with passing CI, deployed to staging, visible in the Friday demo, and documented
(README, runbook or ADR) where someone else would need it.
