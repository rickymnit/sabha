# Sabha

Sabha is a conversation intelligence platform. It turns recorded conversations (lessons, counselling sessions,
front-desk calls, meetings, sales calls) into speaker-labelled transcripts and rubric-based feedback in which every
claim is backed by a timestamped quote.

One multi-tenant product serves schools, colleges and companies. An organisation profile changes labels, default
rubrics and rules, never code. The 8-week pilot covers **teaching and reception in schools**.

> **Status: early development.** The foundations are in place: tooling, CI, local services, settings, the recording
> state machine, time mapping, organisation profiles, design system and rubric drafts. Some pipeline logic (transcript
> assembly, speaker roles, PII redaction) and the evaluation scripts are built and tested on their own. The API,
> workers and the end-to-end pipeline are not built yet. See [Project status](#project-status).

## How it works

```
upload ─► preprocess ─► diarize ─► transcribe ─► analyze ─► report
         (normalise,    (who spoke  (ASR, roles,   (metrics in code,
          VAD)           when)       transcript)    LLM judgement, grounding)
```

1. A client uploads audio **directly to object storage** with presigned multipart URLs. The API only authorises
   the upload and records it.
2. Celery workers run each stage on its own queue (`cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`,
   `billing.meter`). Every stage is idempotent: it writes to `{tenant_id}/{recording_id}/{stage}@{version}/` and
   skips work whose output already exists.
3. Silence is removed for processing but **indexed, not deleted**. Every timestamp shown to a user is on the
   original recording's timeline.
4. Numbers such as talk share, question counts, pace and silence are computed in code. The LLM only makes
   judgements, each judgement must quote the transcript, and a verifier checks every quote before anything is
   shown to users.

A recording moves through `CREATED → UPLOADED → PREPROCESSING → DIARIZING → TRANSCRIBING → ANALYZING → COMPLETED`.
`FAILED` and `NEEDS_REVIEW` can be reached from any worker stage. All transitions are defined in
[`packages/core/sabha_core/state.py`](packages/core/sabha_core/state.py), and nowhere else.

## Non-negotiable rules

The full list is in [`CLAUDE.md`](CLAUDE.md). In short:

- **Tenant isolation.** All data access goes through the tenant-scoped repository, and a query without `tenant_id`
  raises.
- **Consent first.** A recording without `consent_ref` cannot be processed.
- **Staff are analysed, not students.** There are no student-level scores or profiles.
- **No ungrounded claims and no invented metrics.** Quality figures (WER, kappa, accuracy, cost) come only from
  eval scripts run on real, human-annotated data.
- **PII is redacted before every LLM call.** No provider fallback happens silently.
- **Data stays in India:** AWS `ap-south-1` and MongoDB Atlas Mumbai.
- **Secrets come only from environment variables.** Never commit secrets or real recordings.

## Getting started

### Prerequisites

- Linux, macOS or WSL 2, with `make`
- [uv](https://docs.astral.sh/uv/) (installs and manages Python 3.12)
- Node.js 22 and pnpm 10 (`corepack enable` picks the pinned pnpm version)
- Docker with Compose v2, for local services and integration tests

### First run

```bash
make setup     # creates .env from .env.example, installs Python and web dependencies and the git hooks
make dev       # starts MongoDB (single-node replica set), Redis and RustFS, then creates the buckets
uv run python scripts/check_env.py   # validates .env and checks that every service is reachable
pnpm -C apps/web dev                 # web app on http://localhost:5173 (demos at /dev/components, /dev/transcript)
```

`make env` (run by `make setup`) never overwrites an existing `.env`. It fills in random local storage credentials.
OIDC values are added when identity lands (P1.5); until then `check_env.py` reports FAIL for OIDC. Every setting is documented in [`.env.example`](.env.example).

Local services listen on `127.0.0.1` only:

| Service | Port | Notes |
| --- | --- | --- |
| MongoDB 7 | 27017 | Replica set `rs0`, required for transactions and change streams |
| Redis 7 | 6380 | Not 6379, to avoid clashing with a system Redis |
| RustFS (S3 API) | 9000 | Console on 9001. S3-compatible stand-in for AWS S3 ([ADR 0003](docs/adr/0003-local-object-storage.md)) |

Stop the services with `make down`. Data volumes are kept.

### Commands

| Command | What it does |
| --- | --- |
| `make help` | List all commands |
| `make test` | All Python tests (integration tests start containers via testcontainers) and web unit tests |
| `make test-fast` | Tests that need no Docker |
| `make lint` | ruff, mypy (`--strict` on `packages/`), eslint, prettier and tsc |
| `make fmt` | Fix formatting and autofixable lint issues |
| `make logs` | Follow local service logs |
| `make e2e` | Playwright end-to-end tests (not implemented yet, P6.2) |
| `make eval-wer HYP_DIR=<dir>` | Word error rate and role accuracy of system transcripts against the hold-out gold set |
| `make eval-kappa` | Rater agreement on the calibration hold-out set (not implemented yet, P4.6) |

## Repository layout

| Path | Contents |
| --- | --- |
| [`apps/api`](apps/api) | FastAPI service: versioned `/v1` routers, schemas, OIDC auth |
| [`apps/workers`](apps/workers) | Celery workers for each pipeline stage, plus the outbox relay |
| [`apps/web`](apps/web) | React 18 + TypeScript + Vite app. Design tokens and components are in `src/design/` |
| [`packages/core`](packages/core) | `sabha_core`: settings, tenant-scoped repository, models, state machine, time mapping, profiles |
| [`packages/asr`](packages/asr) | `sabha_asr`: multi-provider speech recognition |
| [`packages/llm`](packages/llm) | `sabha_llm`: LLM gateway with routing, budgets, PII redaction, caching and cost accounting |
| [`packages/analytics`](packages/analytics) | `sabha_analytics`: rubric loading, metrics, scoring, grounding and synthesis |
| [`rubrics`](rubrics) | Versioned rubric files: `<type>.<segment>.v<major>.<minor>.yaml` |
| [`eval`](eval) | Gold-set tooling and evaluation scripts. The only source of quality numbers |
| [`infra`](infra) | Docker Compose files, Label Studio for annotators, and Terraform (to come) |
| [`docs`](docs) | ADRs, design references, prompts per week, guides, rubric review sheets, legal drafts |
| [`scripts`](scripts) | Developer helpers: environment check and local bucket setup |

## Stack

Python 3.12 (uv workspaces, ruff, mypy), FastAPI with Pydantic v2, Celery 5 on Redis 7, MongoDB 7 (PyMongo's async
client in the API, the sync client in workers), S3 via boto3, ffmpeg, Silero VAD, pyannote or NeMo Sortformer,
PII redaction in `packages/llm` (regular expressions; Presidio was considered, see P5.2), Langfuse, React 18 with Vite, Tailwind and TanStack Query, and OIDC for identity. Infrastructure uses Docker
Compose, Terraform and GitHub Actions. Reasons for each choice are in
[ADR 0001](docs/adr/0001-repo-and-stack.md).

## Project status

The work follows an 8-week plan, with one Claude Code prompt per task in [`docs/prompts/`](docs/prompts/README.md).
Prompt IDs (for example `P2.4`) match the plan and appear in commit messages.

| Area | State |
| --- | --- |
| Monorepo, tooling, pre-commit hooks, local services (P1.1) | Done |
| CI: lint, tests, security scans; Dockerfiles (P1.2) | Done. Image publishing is off until the API and workers exist |
| Settings and environment check (P0.5) | Done |
| Recording state table, time mapping, organisation profiles (P2.3, P3.3, P1.7, pure parts) | Done |
| Design tokens, components and overview spike (P0.2, P6.1) | Done |
| Teaching and reception rubric drafts v0.1 (P0.8) | Drafts, awaiting review |
| Label Studio setup and gold-set import and export (P4.1) | Done |
| Consent and recording-notice drafts (P8.1), recording guide for schools (P8.3) | Drafts for legal review |
| ASR chunking and batching, speaker roles, transcript assembly (P3.5, P3.6, P3.7, pure parts) | Done. Not yet wired into a worker stage |
| PII redaction (P5.2) | Done. Not yet behind the LLM gateway (P5.1) |
| Gold-set freeze and coverage report, WER and role-accuracy eval (P4.2, P4.3) | Done. Gate targets in `eval/targets.yaml` are unset until baselines exist |
| Transcript view with synced player (P6.5) | Done with mock data, at `/dev/transcript` |
| LLM provider shortlist (P0.6) | o3-mini chosen; details to confirm with OpenAI |
| LIS baselines (P0.7) | Dropped: there is no LIS codebase. ASR providers are chosen by our own bake-off on the gold set |
| API, identity, tenancy, uploads, workers, ASR providers, LLM gateway, scoring, reports | Not started |

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every pull request and every push to `main`:

- **Python:** ruff, mypy and pytest with coverage. Integration tests run against real MongoDB in Docker.
- **Web:** eslint, prettier, tsc, vitest and a production build.
- **Security:** pip-audit, `pnpm audit` and gitleaks over the full history.

The job that builds and pushes images to `ghcr.io` runs only when the repository variable `PUBLISH_IMAGES` is
`true`.

## Contributing

- **Read [`CLAUDE.md`](CLAUDE.md) first.** It holds the rules, conventions and definition of done.
- **Plan before code** for anything bigger than a small fix. Keep each change to one concern and small enough to
  review in under 15 minutes.
- **Add tests with every change.** Tenant isolation, grounding, idempotency and the state machine need tests
  written before the implementation.
- **Explain dependencies and decisions.** Say why you are adding any new dependency. Record architecture
  decisions as ADRs in [`docs/adr/`](docs/adr).
- **Put the prompt ID in commit messages,** for example `P2.4: celery queues per stage with DLQ`.
- **Never commit `.env` files, recordings or gold transcripts.** They are gitignored, and pre-commit runs
  detect-secrets.
