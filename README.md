# Sabha

Sabha is a conversation intelligence platform. It turns recorded conversations (lessons, counselling sessions,
front-desk calls, meetings, sales calls) into speaker-labelled transcripts and rubric-based feedback in which every
claim is backed by a timestamped quote.

One multi-tenant product serves schools, colleges and companies. An organisation profile changes labels, default
rubrics and rules, never code. The 8-week pilot covers **teaching and reception in schools**.

> **Status (29 October 2026).** The pipeline runs end to end on a developer machine: upload in the web app,
> preprocessing, silence detection, speaker diarisation, speech recognition (Sarvam AI), LLM scoring (OpenAI
> `gpt-6-luna`) with verified quotes, and the report. The web app covers recordings, people with their classes and
> sections, overview, reviews and disputes, re-analysis, live status, rubrics, settings, activity (audit log) and
> cost per recording. Besides school teaching and reception, there are draft rubrics for sales meetings, team
> meetings and company reception. It has run only on test recordings, not real school data. Not built yet: staging
> and production on AWS, the Auth0 tenant (local sign-in is used meanwhile), monitoring, webhooks, calibration on
> real rater scores, and consent records in the app (parked for the law team). See
> [Project status](#project-status) and [Running costs](#running-costs).

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

`uv run python scripts/admin/dev_seed.py` creates a local test school, a demo company and users. A full run needs `OPENAI_API_KEY`
and `SARVAM_API_KEY` in `.env`.

`make env` (run by `make setup`) never overwrites an existing `.env`. It fills in random local storage credentials.
Every setting is documented in [`.env.example`](.env.example).

Sign-in uses Auth0 ([ADR 0002](docs/adr/0002-auth.md)). Set `OIDC_ISSUER`, `OIDC_AUDIENCE` and `OIDC_CLIENT_ID` in
`.env`, and the matching `VITE_OIDC_*` values in `apps/web/.env.local` (copy
[`apps/web/.env.example`](apps/web/.env.example)). [`docs/setup/auth.md`](docs/setup/auth.md) explains how to create
the Auth0 tenant and applications. Until the Auth0 tenant exists, use the local dev sign-in instead (`APP_ENV=local`,
`DEV_LOGIN=true`, see [`apps/web/README.md`](apps/web/README.md)): you pick a seeded user on the sign-in page. Or, for a username and
password instead of the list, set `LOGIN_USERNAME`, `LOGIN_PASSWORD_HASH` (from
`uv run python scripts/admin/hash_password.py`) and `LOGIN_AS` in `.env` with `DEV_LOGIN=false`, and
`VITE_AUTH_MODE=password` in `apps/web/.env.local` (local only; [ADR 0002](docs/adr/0002-auth.md) addendum).

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

### Admin scripts

Run from the repo root with `uv run python scripts/admin/<script>`. `backfill.py` and `expire_audio.py` take
`--dry-run`; use it first.

| Script | What it does |
| --- | --- |
| `create_tenant.py` | Create a workspace from a profile (school, college or company) and invite its first owner. There is no self-sign-up |
| `dev_seed.py` | Local only: "Demo School" and the fictional "Brightpath Software", one user per role |
| `set_plan.py` | Change a workspace's plan or monthly audio-hour allowance |
| `hash_password.py` | Make the password hash for the local password sign-in |
| `backfill.py` | Fill in fields added after recordings were processed (speaker strips, speech time, reception tickets) |
| `expire_audio.py` | Run audio retention by hand (the worker scheduler runs it nightly) |
| `restore_drill.py` | Load a database backup into a scratch database and check it; record the result in [`docs/runbook.md`](docs/runbook.md) |

## Repository layout

| Path | Contents |
| --- | --- |
| [`apps/api`](apps/api) | FastAPI service: sign-in, users and invites, classes and teachers, uploads, recordings, results, overview, inbox, search, reviews, disputes, re-analysis, live events, rubrics, settings, usage, costs, audit log, erasure |
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
| [`scripts`](scripts) | Developer helpers (environment check, local bucket setup, synthetic audio) and admin scripts in `scripts/admin/` (see below) |
| [`tests`](tests) | Cross-package security tests: tenant isolation and raw collection access |

## Stack

Python 3.12 (uv workspaces, ruff, mypy), FastAPI with Pydantic v2, Celery 5 on Redis 7, MongoDB 7 (PyMongo's async
client in the API, the sync client in workers), S3 via boto3, ffmpeg, Silero VAD, pyannote on CPU for diarisation
(NeMo Sortformer once there is a GPU), Sarvam AI for speech recognition
([ADR 0006](docs/adr/0006-asr-sarvam.md)), OpenAI `gpt-6-luna` for LLM judgements
([`docs/llm-providers.md`](docs/llm-providers.md)), PII redaction in `packages/llm` (regular expressions; Presidio was
considered, see P5.2), Langfuse, React 18 with Vite, Tailwind and TanStack Query, and Auth0 over OIDC for sign-in
([ADR 0002](docs/adr/0002-auth.md)). Infrastructure uses Docker Compose and Terraform. Reasons for
each choice are in [ADR 0001](docs/adr/0001-repo-and-stack.md).

## Project status

The work follows an 8-week plan, with one Claude Code prompt per task in [`docs/prompts/`](docs/prompts/README.md).
Prompt IDs (for example `P2.4`) match the plan and appear in commit messages.

| Area | State |
| --- | --- |
| Monorepo, tooling, local services, settings (P1.1, P0.5) | Done. GitHub Actions removed on 2026-11-02 ([ADR 0010](docs/adr/0010-no-github-actions.md)) |
| API: errors, request ids, health, rate limits, quotas, permission matrix for every route (P1.4, P7.2, P7.4) | Done |
| Sign-in: Auth0 token checks, web sign-in with PKCE, users, invites, `/v1/me` (P1.5) | Done. The Auth0 tenant itself is set up in week 8; local dev sign-in meanwhile |
| Tenant-scoped repository, models, indexes, isolation tests (P1.6) | Done |
| Uploads: presigned multipart, complete, checksum, duplicates (P2.1, P2.2) | Done |
| Outbox and relay, Celery queues, retries, dead-letter queue, state machine (P2.3, P2.4, P2.5) | Done |
| Preprocess (ffmpeg), silence detection (Silero VAD), diarisation (pyannote, CPU) (P3.2, P3.3, P3.4a) | Done |
| Speech recognition through Sarvam AI, speaker roles, transcript (P3.1, P3.5 to P3.7) | Done |
| LLM gateway, PII redaction, scoring, grounding, synthesis, analyze stage (P5.1, P5.2, P5.4 to P5.7) | Done |
| Reception: ticket, hold metric, not-applicable dimensions, rubric v0.2 (P5.8) | Done. Teaching rubric is v0.1 |
| Sales meetings (rubric v0.2, deal card), team meetings scored as a whole with notes ([ADR 0008](docs/adr/0008-meetings.md)), company reception (rubric v0.1) | Done as drafts for the owner's review. Demo company "Brightpath Software" in the dev seed |
| Read API and web app on real data: recordings, report, upload, people, overview, inbox, search (P5.7b, P6.2, P6.4b, P6.6) | Done. Restyled to the v2 design for tokens, sidebar and Overview; other pages in progress |
| Classes and sections (two-level units), teachers with the class-sections they teach | Done (owners and admins) |
| Reviews: queue, "who is the speaker?", resolve ([ADR 0007](docs/adr/0007-review-outcomes.md)) | Done |
| Disputes: raise, queue, decide, email; the reviewer's score replaces the AI's (P6.7) | Done |
| Re-analysis of one or many recordings, every version kept (P2.8) | Done. Choosing a rubric version is in the API only |
| Live status over server-sent events (P2.6) | Done |
| Settings, rubrics pages, role views, accessibility checks, browser tests per role (P1.7, P6.8) | Done. Rubric editing waits for calibration |
| Plans and audio-hour allowances, upload pause at the limit, cost in rupees per recording (P6.2, P7.2) | Done. Rate limiter and the 80 % warning email remain |
| Audit log and Activity page, retry or close a failed recording (P1.8, P7.8) | Done. Pause per tenant and usage export remain |
| Audio retention, erasure on request, nightly database export and restore drill (P7.3) | Done locally. Atlas backup and bucket lifecycle come with AWS |
| Status emails (P2.7) | Done. Webhooks not wired yet |
| Evaluation tools: gold set, WER, role accuracy, AI-human agreement, grounding, rater kit (P4.1 to P4.6) | Tools done. No real gold set yet, so no quality figures |
| Model bake-off, calibration, CI eval gate, NeMo Sortformer on GPU (P5.3, P5.9, P4.7, P3.4b) | Not started. Needs real annotated recordings (and a GPU) |
| Consent records in the app (P6.9) | Parked for the law team. Consent is still required at upload (golden rule 9) |
| AWS staging and production, Terraform, monitoring, Auth0 tenant | Planned for week 8 |

## Running costs

This section lists what Sabha pays for, what has been measured so far and which savings are already built in, so
that cost ideas can be weighed against facts. Every figure below comes from our own stored records (`llm_calls`,
`stage_runs`) or a provider's published price list, with the date. Nothing is estimated (golden rule 6).

### What costs money

| Item | Paid per | What we know |
| --- | --- | --- |
| LLM: OpenAI `gpt-6-luna` | Token | $0.10 per million input tokens, $0.50 per million output, cached input $0.01, cache writes $0.125 (OpenAI model page, 2026-10-24). Every call is recorded with tokens and cost in `llm_calls` |
| Speech recognition: Sarvam AI REST API (`saaras:v4`) | Minute of audio sent | ₹0.49 per minute pay as you go; ₹0.45, ₹0.41 and ₹0.38 on the Pro, Growth and Business plans (sarvam.ai/api-pricing, 2026-10-28; in [`sabha_asr/pricing.py`](packages/asr/sabha_asr/pricing.py)). Audio goes in chunks of at most 30 s, after silence is removed |
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
- These runs predate the cost card, so their Sarvam cost was not recorded. Since 2026-10-28 every recording shows
  an expected cost at upload and its actual cost in rupees when done (speech recognition from Sarvam's published
  price, LLM from `llm_calls`, converted at `USD_INR_RATE` when it is set).

### Savings already built in

- Silence is cut before transcription (VAD), so speech recognition only receives speech.
- Scoring groups rubric dimensions, at most 3 calls per recording, and only a failed dimension is asked again, once.
- Numbers (talk share, questions, pace, silence) are computed in code, not by the LLM.
- Every stage is idempotent: a retry skips work whose output already exists, and duplicate uploads are detected
  by checksum.
- Monthly audio-hour allowances per plan: Starter uploads pause at the limit (`scripts/admin/set_plan.py` changes
  one customer's).
- Original audio is deleted by a nightly job after the workspace's retention period (90 days by default).
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
- Would a Sarvam plan, or a self-hosted speech model in India, cost less than pay as you go at pilot volume?
- Would OpenAI's Batch API or a lower reasoning effort cut LLM cost without hurting agreement with raters?
- Why does the prompt cache not hit between the two scoring calls, and is caching worth it with `gpt-6-luna`?
- Audio is kept 90 days by default. How long should artefacts be kept, and when can they move to cheaper S3
  storage classes?
- Expected pilot volume (recordings per school per week, average length) is not set yet, so monthly totals
  cannot be worked out.


## Checks before pushing

There is no CI: pushes to GitHub run nothing ([ADR 0010](docs/adr/0010-no-github-actions.md)). Run the checks
locally before pushing:

- `make lint`: ruff, mypy, eslint and tsc.
- `make test`: Python tests (integration tests against real MongoDB in Docker) and web unit tests.
- pre-commit runs detect-secrets on every commit.

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
