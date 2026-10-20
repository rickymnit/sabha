# ADR 0001: Repository layout and technology stack

- **Status:** Proposed
- **Date:** 2026-10-14
- **Plan task:** 0.2

## Context

Sabha turns recorded conversations into speaker-labelled transcripts and rubric-based, evidence-backed
feedback for schools, colleges and companies. The 8-week pilot covers teaching and reception for schools.
The system must keep data in India, isolate tenants strictly, run a GPU speech pipeline and an LLM scoring
stage reliably, and be small enough for one team to operate.

Correction (2026-10-17): an earlier version said speech recognition would be ported from a "Lecture Intelligence
System (LIS)". No such codebase exists; `packages/asr` is built here.

## Decision

One monorepo with the layout in `CLAUDE.md`:

```
apps/api, apps/workers, apps/web
packages/core, packages/asr, packages/llm, packages/analytics
rubrics/, eval/, infra/, docs/
```

Python packages under `packages/` hold all shared logic; `apps/` are thin entry points. Rubrics are data
files, not code, so organisation profiles change labels, rubrics and rules without code changes.

Stack:

| Area | Choice |
| --- | --- |
| Python | 3.12, `uv` workspaces, `ruff`, `mypy --strict` on `packages/` |
| API | FastAPI, Pydantic v2, Uvicorn; async MongoDB via `pymongo.AsyncMongoClient` (PyMongo 4.9+, not Motor) |
| Workers | Celery 5 on Redis 7; sync `pymongo.MongoClient` inside tasks |
| Database | MongoDB 7 replica set (transactions and change streams required, also in tests) |
| Storage | S3 (`ap-south-1`) in staging and prod, RustFS locally (ADR 0003; originally MinIO); boto3 |
| Audio | ffmpeg/ffprobe, Silero VAD, pyannote or NeMo Sortformer, ASR via `packages/asr` |
| LLM | `packages/llm` gateway (routing, budgets, retries, caching), Langfuse tracing, Presidio redaction |
| Web | React 18 + TypeScript + Vite, Tailwind, TanStack Query, React Router, Vitest, Playwright |
| Auth | OIDC with Auth0 (ADR 0002); JWT validated in the API |
| Infra | Docker Compose (dev, staging, prod pilot), Terraform for AWS, GitHub Actions |
| Observability | OpenTelemetry, Prometheus, Grafana, Sentry, structured JSON logs |

### Web versions fixed by the Week 0 spike

| Package | Version | Why this one |
| --- | --- | --- |
| React | 18.3.1 | The stack says React 18; current Vite templates default to 19. |
| Tailwind CSS | 3.4.19 | Plan tasks 0.2 and 6.1 expect a `tailwind.config.ts`; Tailwind 4 moves configuration into CSS. Revisit after the pilot. |
| TypeScript | 5.9.3 | TypeScript 7 is the new native compiler; lint tooling added in P1.1 may not support it yet. |
| Vite | 8.3.1 | Current major release. |
| Instrument Sans | `@fontsource/instrument-sans` 5.3.0 | Self-hosted, so pages make no requests to an outside font service (golden rule 12). |
| Package manager | pnpm 10 | As in `CLAUDE.md` commands. |

## Consequences

- One repository means one CI pipeline, one review flow and atomic changes across API, workers and web.
- Shared Python logic in `packages/` must stay free of app-specific imports; `mypy --strict` there enforces
  typed interfaces between apps.
- MongoDB must run as a replica set everywhere, including local dev and tests, which makes Docker a hard
  requirement for development.
- Choosing AWS `ap-south-1` and Atlas Mumbai keeps data in India; any service hosted elsewhere (for example an
  LLM provider or SaaS monitoring) needs an explicit decision before it is added.
- Pinning React 18 and Tailwind 3 trades newer features for stability during the pilot; upgrading either is a
  separate, later change.
