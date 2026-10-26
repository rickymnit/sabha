# Sabha

Sabha is a conversation intelligence platform. It turns recorded conversations (lessons, counselling sessions,
front-desk calls, meetings, sales calls) into speaker-labelled transcripts and rubric-based feedback in which every
claim is backed by a timestamped quote.

One multi-tenant product serves schools, colleges and companies. An organisation profile changes labels, default
rubrics and rules, never code. The 8-week pilot covers **teaching and reception in schools**.

> **Status: pilot week 2 (October 2026).** The pipeline runs end to end on a developer machine: upload in the web
> app, preprocessing, silence detection, speaker diarisation, speech recognition (Sarvam AI), LLM scoring
> (OpenAI `gpt-6-luna`) with verified quotes, and the report, recordings list, people, overview and review pages on
> real data. It has run only on test recordings, not real school data. Not built yet: staging and production on AWS,
> the Auth0 tenant (local dev sign-in is used meanwhile), disputes, consent records in the app, retention and
> erasure, monitoring, and the sales, meeting and company-reception profiles. See [Project status](#project-status)
> and [Running costs](#running-costs).

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
make setup          # creates .env from .env.example, installs Python and web dependencies, git hooks and the VAD model
make setup-speech   # pyannote and CPU PyTorch for diarisation, and its model (needs HF_TOKEN in .env)
make dev            # starts MongoDB (single-node replica set), Redis and RustFS, then creates the buckets
uv run python scripts/check_env.py   # validates .env and checks that every service is reachable
make api                             # API on http://localhost:8000; /docs lists the endpoints
make relay                           # outbox relay: starts pipeline stages when an upload completes
make workers                         # one Celery worker for every queue
make beat                            # scheduler: stale-upload cleanup and stuck-job sweeper
pnpm -C apps/web dev                 # web app on http://localhost:5180
```

`uv run python scripts/admin/dev_seed.py` creates a local test school and users. A full run needs `OPENAI_API_KEY`
and `SARVAM_API_KEY` in `.env`.

`make env` (run by `make setup`) never overwrites an existing `.env`. It fills in random local storage credentials.
Every setting is documented in [`.env.example`](.env.example).

Sign-in uses Auth0 ([ADR 0002](docs/adr/0002-auth.md)). Set `OIDC_ISSUER`, `OIDC_AUDIENCE` and `OIDC_CLIENT_ID` in
`.env`, and the matching `VITE_OIDC_*` values in `apps/web/.env.local` (copy
[`apps/web/.env.example`](apps/web/.env.example)). [`docs/setup/auth.md`](docs/setup/auth.md) explains how to create
the Auth0 tenant and applications. Until the Auth0 tenant exists, use the local dev sign-in instead (`APP_ENV=local`,
`DEV_LOGIN=true`, see [`apps/web/README.md`](apps/web/README.md)): you pick a seeded user on the sign-in page.

In development the web app also serves demo pages on mock data, with no sign-in: `/dev/components`,
`/dev/transcript`, `/dev/report`, `/dev/reviews` and `/dev/overview`.

Speech recognition uses Sarvam AI ([ADR 0006](docs/adr/0006-asr-sarvam.md)). To try it alone, run
`uv run sabha-asr-transcribe <file.wav>` on a 16 kHz mono WAV file. Only send audio you have consent for, and no real
recordings until Sarvam's and OpenAI's data terms are confirmed in writing.

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
| `make api` | Run the API with reload on http://localhost:8000 (needs `make dev` and the OIDC values in `.env`) |
| `make workers` / `make relay` / `make beat` | Run the Celery workers, the outbox relay and the scheduler |
| `make setup-speech` | Install the diarisation extra (pyannote, CPU PyTorch) and fetch its model |
| `make test` | All Python tests (integration tests start containers via testcontainers) and web unit tests |
| `make test-fast` | Tests that need no Docker |
| `make lint` | ruff, mypy (`--strict` on `packages/`), eslint, prettier and tsc |
| `make fmt` | Fix formatting and autofixable lint issues |
| `make logs` | Follow local service logs |
| `make e2e` | Playwright browser smoke tests against the running stack |
| `make eval-wer HYP_DIR=<dir>` | Word error rate and role accuracy of system transcripts against the hold-out gold set |
| `make eval-kappa RUBRIC=<yaml> AI_DIR=<dir> SCORES="<files>"` | AI-human agreement and grounding on the calibration hold-out set |

## Repository layout

| Path | Contents |
| --- | --- |
| [`apps/api`](apps/api) | FastAPI service: sign-in, users and invites, uploads, recordings, results, overview, reviews |
| [`apps/workers`](apps/workers) | Celery workers: pipeline stages in `stages/`, outbox relay, notifications, cleanup and the fair GPU scheduler |
| [`apps/web`](apps/web) | React 18 + TypeScript + Vite app. Design tokens and components are in `src/design/` |
| [`packages/core`](packages/core) | `sabha_core`: settings, tenant-scoped repository, models, state machine, time mapping, profiles |
| [`packages/asr`](packages/asr) | `sabha_asr`: provider layer (Sarvam AI), chunking, batching, speaker roles and transcript assembly |
| [`packages/llm`](packages/llm) | `sabha_llm`: the gateway (routing, budgets, retries, cost accounting in `llm_calls`) and PII redaction |
| [`packages/analytics`](packages/analytics) | `sabha_analytics`: rubric loading, metrics, scoring, grounding and synthesis |
| [`rubrics`](rubrics) | Versioned rubric files: `<type>.<segment>.v<major>.<minor>.yaml` |
| [`eval`](eval) | Gold-set tooling and evaluation scripts. The only source of quality numbers |
| [`infra`](infra) | Docker Compose files, Label Studio for annotators, and Terraform (to come) |
| [`docs`](docs) | ADRs, setup guides, design references, prompts per week, school guides, rater kit, rubric review sheets, legal drafts |
| [`scripts`](scripts) | Developer helpers: environment check and local bucket setup |
| [`tests`](tests) | Cross-package security tests: tenant isolation and raw collection access |

## Stack

Python 3.12 (uv workspaces, ruff, mypy), FastAPI with Pydantic v2, Celery 5 on Redis 7, MongoDB 7 (PyMongo's async
client in the API, the sync client in workers), S3 via boto3, ffmpeg, Silero VAD, pyannote on CPU for diarisation
(NeMo Sortformer once there is a GPU), Sarvam AI for speech recognition
([ADR 0006](docs/adr/0006-asr-sarvam.md)), OpenAI `gpt-6-luna` for LLM judgements
([`docs/llm-providers.md`](docs/llm-providers.md)), PII redaction in `packages/llm` (regular expressions; Presidio was
considered, see P5.2), Langfuse, React 18 with Vite, Tailwind and TanStack Query, and Auth0 over OIDC for sign-in
([ADR 0002](docs/adr/0002-auth.md)). Infrastructure uses Docker Compose, Terraform and GitHub Actions. Reasons for
each choice are in [ADR 0001](docs/adr/0001-repo-and-stack.md).

## Project status

The work follows an 8-week plan, with one Claude Code prompt per task in [`docs/prompts/`](docs/prompts/README.md).
Prompt IDs (for example `P2.4`) match the plan and appear in commit messages.

| Area | State |
| --- | --- |
| Monorepo, tooling, CI, local services, settings (P1.1, P1.2, P0.5) | Done. Image publishing stays off until staging |
| API: errors, request ids, health, rate limits, quotas, permission matrix for every route (P1.4, P7.2, P7.4) | Done |
| Sign-in: Auth0 token checks, web sign-in with PKCE, users, invites, `/v1/me` (P1.5) | Done. The Auth0 tenant itself is set up in week 8; local dev sign-in meanwhile |
| Tenant-scoped repository, models, indexes, isolation tests (P1.6) | Done |
| Uploads: presigned multipart, complete, checksum, duplicates (P2.1, P2.2) | Done |
| Outbox and relay, Celery queues, retries, dead-letter queue, state machine (P2.3, P2.4, P2.5) | Done |
| Preprocess (ffmpeg), silence detection (Silero VAD), diarisation (pyannote, CPU) (P3.2, P3.3, P3.4a) | Done |
| Speech recognition through Sarvam AI, speaker roles, transcript (P3.1, P3.5 to P3.7) | Done |
| LLM gateway, PII redaction, scoring, grounding, synthesis, analyze stage (P5.1, P5.2, P5.4 to P5.7) | Done |
| Reception: ticket, hold metric, not-applicable dimensions, rubric v0.2 (P5.8) | Done. Teaching rubric is v0.1 |
| Read API and web app on real data: recordings, report, upload, people, overview (P5.7b, P6.2, P6.4b, P6.6) | Done |
| Reviews: queue, "who is the speaker?", resolve (ADR 0007) | Done |
| Status emails (P2.7) | Done. Webhooks not wired yet |
| Evaluation tools: gold set, WER, role accuracy, AI-human agreement, grounding, rater kit (P4.1 to P4.6) | Tools done. No real gold set yet, so no quality figures |
| Sales calls, meetings, company reception (new organisation profiles and rubrics) | Not started. Next priority |
| Disputes API, consent records in the app, retention and erasure, re-analysis | Not started |
| AWS staging and production, Terraform, monitoring, Auth0 tenant | Planned for week 8 |

## Running costs

This section lists what Sabha pays for, what has been measured so far and which savings are already built in, so
that cost ideas can be weighed against facts. Every figure below comes from our own stored records (`llm_calls`,
`stage_runs`) or a provider's published price list, with the date. Nothing is estimated (golden rule 6).

### What costs money

| Item | Paid per | What we know |
| --- | --- | --- |
| LLM: OpenAI `gpt-6-luna` | Token | $0.10 per million input tokens, $0.50 per million output, cached input $0.01, cache writes $0.125 (OpenAI model page, 2026-10-24). Every call is recorded with tokens and cost in `llm_calls` |
| Speech recognition: Sarvam AI REST API | Audio sent | Audio goes in chunks of at most 30 s, after silence is removed. Price not yet recorded in [ADR 0006](docs/adr/0006-asr-sarvam.md) |
| Diarisation: pyannote on CPU | Compute time | Open model, no licence fee. The slowest stage by far (see below) |
| Preprocessing and VAD: ffmpeg, Silero | Compute time | Open source, runs on CPU |
| Hosting: AWS `ap-south-1` (S3 with 3 buckets, servers for API, workers, Redis), MongoDB Atlas Mumbai | Month | Not priced yet. Must stay in India (golden rule 12) |
| Sign-in (Auth0), email (Amazon SES), error tracking (Sentry) | Month or usage | Not priced yet |

### Measured so far

Three test recordings on a developer laptop (WSL, 3 GB RAM, no GPU). These are single runs on test audio, not
averages over real school recordings.

| Recording | LLM calls and cost | Preprocess | Diarisation | Transcription | Analysis |
| --- | --- | --- | --- | --- | --- |
| 3 min lesson, 2026-10-22, `o3-mini` (since shut down) | 4 calls, $0.066 | 11 s | 172 s | 5 s | 70 s |
| 19.8 min lecture, 2026-10-26, `gpt-6-luna` | 4 calls, $0.0068 | 74 s | 1,326 s | 49 s | ended `analysis_failed` |
| 28.2 min lecture, 2026-10-26, `gpt-6-luna` | 4 calls, $0.0066 | 117 s | 1,676 s | 49 s | ended `analysis_failed` |

What these show:

- **Diarisation on CPU takes about as long as the recording itself**, about 90% of the processing time on the two
  long recordings. It is the main compute cost and the main reason a report takes as long as it does.
- **LLM cost per recording is under one cent with `gpt-6-luna`**, whose token prices are about a tenth of
  `o3-mini`'s. Each
  analysis makes 2 scoring calls (about 10,000 input and 2,000 to 3,000 output tokens each), 1 synthesis call and
  1 segmentation call.
- **The prompt cache did not hit.** The second scoring call repeats the same 10,000-token prefix but recorded
  `cached_tokens: 0` and a cache write instead. With `gpt-6-luna`, a cache write costs more than plain input.
- The Sarvam cost per recording is not recorded yet.

### Savings already built in

- Silence is cut before transcription (VAD), so speech recognition only receives speech.
- Scoring groups rubric dimensions, at most 3 calls per recording, and only a failed dimension is asked again, once.
- Numbers (talk share, questions, pace, silence) are computed in code, not by the LLM.
- Every stage is idempotent: a retry skips work whose output already exists, and duplicate uploads are detected
  by checksum.
- Daily token budgets per tenant and overall exist in the gateway (`LLM_TENANT_DAILY_TOKEN_BUDGET`,
  `LLM_GLOBAL_DAILY_TOKEN_BUDGET`) but are not set yet.
- Priority lanes and a fair scheduler share processing capacity between tenants
  ([ADR 0005](docs/adr/0005-fairness.md)), so one busy school cannot force extra machines for everyone.

### Limits on any cost saving

A saving cannot break these: data stays in India; PII is redacted before any LLM call; every judgement cites quotes
that are checked against the transcript; no provider is swapped silently; staff are analysed, never students; and
quality figures come only from evaluation on real, human-rated recordings. The full rules are in
[`CLAUDE.md`](CLAUDE.md).

### Open questions

- Is a GPU (for diarisation, and later NeMo Sortformer) cheaper per recording hour than CPU, at pilot volume?
- Should diarisation run on a cheaper or spot machine, since reports are not needed in real time?
- What does Sarvam charge per audio hour, and would a self-hosted speech model in India cost less?
- Would OpenAI's Batch API or a lower reasoning effort cut LLM cost without hurting agreement with raters?
- Why does the prompt cache not hit between the two scoring calls, and is caching worth it with `gpt-6-luna`?
- How long should audio and artefacts be kept, and when can they move to cheaper S3 storage classes?
- Expected pilot volume (recordings per school per week, average length) is not set yet, so monthly totals
  cannot be worked out.


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
