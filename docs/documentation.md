# Sabha documentation

Every document in the repository in one file, built on 2026-11-19 by `scripts/build_documentation.py`. The separate files are the source: edit them, not this file, then run `uv run python scripts/build_documentation.py` again.

## Contents

1. [Overview](#part-1)
   - [Sabha](#doc-readme-md)
   - [docs](#doc-docs-readme-md)
2. [Rules for every change](#part-2)
   - [Sabha — Conversation Intelligence Platform](#doc-claude-md)
3. [Running Sabha](#part-3)
   - [Sabha: every command to run it by hand](#doc-commands-md)
   - [Runbook](#doc-docs-runbook-md)
4. [Components](#part-4)
   - [apps/api](#doc-apps-api-readme-md)
   - [apps/workers](#doc-apps-workers-readme-md)
   - [apps/web](#doc-apps-web-readme-md)
   - [packages/core](#doc-packages-core-readme-md)
   - [packages/asr](#doc-packages-asr-readme-md)
   - [packages/llm](#doc-packages-llm-readme-md)
   - [packages/analytics](#doc-packages-analytics-readme-md)
   - [rubrics](#doc-rubrics-readme-md)
   - [infra](#doc-infra-readme-md)
   - [Label Studio for gold transcripts (plan task P4.1)](#doc-infra-annotation-readme-md)
   - [eval](#doc-eval-readme-md)
   - [eval/goldset](#doc-eval-goldset-readme-md)
5. [Decisions (ADRs)](#part-5)
   - [ADR 0001: Repository layout and technology stack](#doc-docs-adr-0001-repo-and-stack-md)
   - [ADR 0002: Identity provider for login](#doc-docs-adr-0002-auth-md)
   - [ADR 0003: RustFS for local object storage](#doc-docs-adr-0003-local-object-storage-md)
   - [ADR 0005: Fair GPU scheduling across tenants](#doc-docs-adr-0005-fairness-md)
   - [ADR 0006: Sarvam AI for speech recognition, with approximate word timing](#doc-docs-adr-0006-asr-sarvam-md)
   - [ADR 0007: How a recording leaves "Needs review"](#doc-docs-adr-0007-review-outcomes-md)
   - [ADR 0008: Meetings are analysed as a whole](#doc-docs-adr-0008-meetings-md)
   - [ADR 0009: Meeting transcripts can be uploaded instead of audio](#doc-docs-adr-0009-transcript-upload-md)
   - [ADR 0010: No GitHub Actions](#doc-docs-adr-0010-no-github-actions-md)
   - [ADR 0011: Evidence-based speaker roles for support calls](#doc-docs-adr-0011-evidence-based-speaker-roles-md)
   - [ADR 0012: More speech-to-text providers, and comparing them on our own calls](#doc-docs-adr-0012-more-asr-providers-md)
   - [ADR 0013: What the agent said well and badly, checked against product information](#doc-docs-adr-0013-said-well-and-badly-md)
   - [ADR 0014: Number of speakers and the Gemini speaker check, chosen at upload](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)
   - [ADR 0015: Support calls a colleague helped on stay the first agent's](#doc-docs-adr-0015-colleague-helped-calls-md)
   - [ADR 0016: Automated tests removed](#doc-docs-adr-0016-no-automated-tests-md)
6. [Reference](#part-6)
   - [LLM providers](#doc-docs-llm-providers-md)
   - [Sabha webhooks](#doc-docs-webhooks-md)
   - [Security findings (plan task P7.6)](#doc-docs-security-findings-md)
   - [permissions.yaml](#doc-docs-security-permissions-yaml)
   - [Design tokens](#doc-docs-design-tokens-md)
   - [Setting up sign-in (Auth0)](#doc-docs-setup-auth-md)
   - [Cloud setup checklist](#doc-docs-setup-cloud-checklist-md)
7. [Quality and evaluation](#part-7)
   - [Annotation guidelines: gold transcripts](#doc-docs-annotation-guidelines-md)
   - [Rater guide: scoring lessons with the teaching rubric](#doc-docs-raters-guide-md)
   - [Rubric review sheets (draft v0.1)](#doc-docs-rubrics-review-sheet-md)
8. [For schools](#part-8)
   - [Recording guide for teachers and front-desk staff · रिकॉर्डिंग गाइड](#doc-docs-guides-recording-guide-md)
9. [Legal drafts (waiting for the law team)](#part-9)
   - [Spoken recording notice for school reception calls](#doc-docs-legal-drafts-call-recording-notice-md)
   - [Parent consent form: recording classroom lessons for teacher development](#doc-docs-legal-drafts-parent-consent-form-md)
   - [Questions for legal review: Sabha pilot in schools](#doc-docs-legal-drafts-questions-for-lawyer-md)
   - [Staff notice and consent: recording and feedback for teachers, counsellors and front-desk staff](#doc-docs-legal-drafts-staff-consent-and-notice-md)
10. [Appendix: the 8-week plan (history, kept as written)](#part-10)
   - [Claude Code prompts for Sabha](#doc-docs-prompts-readme-md)
   - [Everyday prompt library](#doc-docs-prompts-library-md)
   - [Week 1 — Foundations and upload](#doc-docs-prompts-week-1-md)
   - [Week 2 — Orchestration and the first half of the audio pipeline](#doc-docs-prompts-week-2-md)
   - [Week 3 — Speech-to-text, model choices and Gate 1](#doc-docs-prompts-week-3-md)
   - [Week 4 — Scoring engine and the teaching report](#doc-docs-prompts-week-4-md)
   - [Week 5 — Reception, disputes and fairness](#doc-docs-prompts-week-5-md)
   - [Week 6 — Calibration, Gate 2 and feature freeze](#doc-docs-prompts-week-6-md)
   - [Week 7 — Hardening and pilot readiness](#doc-docs-prompts-week-7-md)
   - [Week 8 — Pilot go-live and buffer](#doc-docs-prompts-week-8-md)

---

<a id="part-1"></a>

# Part 1. Overview

<a id="doc-readme-md"></a>

## Sabha

*Source: [`README.md`](../README.md)*

Sabha is a conversation intelligence platform. It turns recorded conversations (lessons, counselling sessions,
front-desk calls, meetings, sales calls) into speaker-labelled transcripts and rubric-based feedback in which every
claim is backed by a timestamped quote.

One multi-tenant product serves schools, colleges and companies. An organisation profile changes labels, default
rubrics and rules, never code. The 8-week pilot covers **teaching and reception in schools**.

> **Status (19 November 2026).** The pipeline runs end to end on a developer machine: upload in the web app (or a
> meeting recorded in the browser), preprocessing, silence detection, speaker diarisation, speech recognition, LLM
> scoring (OpenAI `gpt-6-luna`) with verified quotes, and the report. Speech recognition can use Sarvam AI (the
> default), Gemini (3.8 Flash, 3.1 Flash-Lite, Flash-Lite), Deepgram, OpenAI, Groq or a self-hosted Whisper; owners
> and admins pick the model at upload, and `eval/asr_compare.py` compares models on calls already transcribed
> ([ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)). Transcripts are written only in English, Hindi and Hinglish.
> Whoever uploads can set the number of speakers and ask Gemini to check who said each line
> ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)), and mark a support call a colleague helped
> on, which stays the first agent's ([ADR 0015](#doc-docs-adr-0015-colleague-helped-calls-md)). There are no automated
> tests since 19 November ([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)).
> Meeting transcripts from Google Meet can be uploaded instead of audio ([ADR 0009](#doc-docs-adr-0009-transcript-upload-md)).
> The web app covers conversations, people with their classes and sections, overview, reviews and disputes,
> re-analysis, sharing, live status, rubrics, approved product information, settings, activity (audit log), cost per
> recording and dark mode. Pages answer first: a sentence and three cards, scores in words, detail behind a click.
> Sales reps get their own workspace (overview, interactions, next actions, private coaching). Besides school
> teaching and reception, there are draft rubrics for sales calls and meetings, support calls, team meetings and
> company reception, and the demo company is NiaLabs. It has run on test recordings and NiaLabs demo calls, not real
> school data. Not built yet: staging and production on AWS, the Auth0 tenant (local sign-in is used meanwhile),
> monitoring, webhooks, calibration on real rater scores, a hand-corrected gold set, and consent records in the app
> (parked for the law team). See [Project status](#project-status) and [Running costs](#running-costs).

### How it works

```
upload ─► preprocess ─► diarize ─► transcribe ─► analyze ─► report
         (normalise,    (who spoke  (ASR, roles,   (metrics in code,
          VAD)           when)       optional       LLM judgement, grounding)
                                     Gemini check,
                                     transcript)
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
[`packages/core/sabha_core/state.py`](../packages/core/sabha_core/state.py), and nowhere else.

### Non-negotiable rules

The full list is in [`CLAUDE.md`](#doc-claude-md). In short:

- **Tenant isolation.** All data access goes through the tenant-scoped repository, and a query without `tenant_id`
  raises.
- **Consent first.** A recording without `consent_ref` cannot be processed.
- **Staff are analysed, not students.** There are no student-level scores or profiles.
- **No ungrounded claims and no invented metrics.** Quality figures (WER, kappa, accuracy, cost) come only from
  eval scripts run on real, human-annotated data.
- **PII is redacted before every LLM call.** No provider fallback happens silently.
- **Data stays in India:** AWS `ap-south-1` and MongoDB Atlas Mumbai. The one exception, approved by the owner,
  is speech recognition providers outside India ([ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)).
- **Secrets come only from environment variables.** Never commit secrets or real recordings.

### Getting started

#### Prerequisites

- Linux, macOS or WSL 2, with `make`
- [uv](https://docs.astral.sh/uv/) (installs and manages Python 3.12)
- Node.js 22 and pnpm 10 (`corepack enable` picks the pinned pnpm version)
- Docker with Compose v2, for local services

#### First run

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

Every command for running Sabha by hand on one machine (start, check, logs, stop, restart after code changes,
troubleshooting) is in [`commands.md`](#doc-commands-md). The API reloads by itself after a code change; the relay and
workers must be restarted.

`uv run python scripts/admin/dev_seed.py` creates a local test school, a demo company and users. A full run needs `OPENAI_API_KEY`
and `SARVAM_API_KEY` in `.env`.

`make env` (run by `make setup`) never overwrites an existing `.env`. It fills in random local storage credentials.
Every setting is documented in [`.env.example`](../.env.example).

Sign-in uses Auth0 ([ADR 0002](#doc-docs-adr-0002-auth-md)). Set `OIDC_ISSUER`, `OIDC_AUDIENCE` and `OIDC_CLIENT_ID` in
`.env`, and the matching `VITE_OIDC_*` values in `apps/web/.env.local` (copy
[`apps/web/.env.example`](../apps/web/.env.example)). [`docs/setup/auth.md`](#doc-docs-setup-auth-md) explains how to create
the Auth0 tenant and applications. Until the Auth0 tenant exists, use the local dev sign-in instead (`APP_ENV=local`,
`DEV_LOGIN=true`, see [`apps/web/README.md`](#doc-apps-web-readme-md)): you pick a seeded user on the sign-in page. Or, for a username and
password instead of the list, set `LOGIN_USERNAME`, `LOGIN_PASSWORD_HASH` (from
`uv run python scripts/admin/hash_password.py`) and `LOGIN_AS` in `.env` with `DEV_LOGIN=false`, and
`VITE_AUTH_MODE=password` in `apps/web/.env.local` (local only; [ADR 0002](#doc-docs-adr-0002-auth-md) addendum).

Speech recognition uses Sarvam AI by default ([ADR 0006](#doc-docs-adr-0006-asr-sarvam-md)). Other providers are
`gemini`, `deepgram`, `openai`, `groq`, `qwen`, `aws` and `whisper` ([ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)).
Choose one with `ASR_PROVIDER` and `ASR_MODEL` in `.env` (each needs its own key, see [`.env.example`](../.env.example))
and restart the workers. Owners and admins can also pick the model per upload; that list leaves out Qwen and Amazon
Transcribe (kept for comparisons only). The upload page also asks the number of speakers and whether Gemini should
check who said each line, which needs `GEMINI_API_KEY` ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)). To try one alone, run
`uv run sabha-asr-transcribe <file.wav>` on a 16 kHz mono WAV file. To compare models on calls already transcribed
with Sarvam:

```bash
uv run python eval/asr_compare.py --tenant demo-company --models gemini,deepgram:nova-3 --latest 3
```

The report goes to `eval/reports/asr-compare-<date>/` (git-ignored: it holds transcripts). It shows each model's
price, speed and how much it differs from Sarvam. That difference is not accuracy: only `eval/wer.py` on a
hand-corrected gold set gives accuracy. Only send audio you have consent for.

Local services listen on `127.0.0.1` only:

| Service | Port | Notes |
| --- | --- | --- |
| MongoDB 7 | 27017 | Replica set `rs0`, required for transactions and change streams |
| Redis 7 | 6380 | Not 6379, to avoid clashing with a system Redis |
| RustFS (S3 API) | 9000 | Console on 9001. S3-compatible stand-in for AWS S3 ([ADR 0003](#doc-docs-adr-0003-local-object-storage-md)) |

Stop the services with `make down`. Data volumes are kept.

#### Commands

| Command | What it does |
| --- | --- |
| `make help` | List all commands |
| `make api` | Run the API with reload on http://localhost:8000 (needs `make dev` and the OIDC values in `.env`) |
| `make workers` / `make relay` / `make beat` | Run the Celery workers, the outbox relay and the scheduler |
| `make setup-speech` | Install the diarisation extra (pyannote, CPU PyTorch) and fetch its model |
| `make lint` | ruff, mypy (`--strict` on `packages/`), eslint, prettier and tsc |
| `make fmt` | Fix formatting and autofixable lint issues |
| `make logs` | Follow local service logs |
| `make eval-wer HYP_DIR=<dir>` | Word error rate and role accuracy of system transcripts against the hold-out gold set |
| `make eval-kappa RUBRIC=<yaml> AI_DIR=<dir> SCORES="<files>"` | AI-human agreement and grounding on the calibration hold-out set |

#### Admin scripts

Run from the repo root with `uv run python scripts/admin/<script>`. `backfill.py` and `expire_audio.py` take
`--dry-run`; use it first.

| Script | What it does |
| --- | --- |
| `create_tenant.py` | Create a workspace from a profile (school, college or company) and invite its first owner. There is no self-sign-up |
| `dev_seed.py` | Local only: "Demo School" and the demo company "NiaLabs", one user per role |
| `set_plan.py` | Change a workspace's plan or monthly audio-hour allowance |
| `hash_password.py` | Make the password hash for the local password sign-in |
| `backfill.py` | Fill in fields added after recordings were processed (speaker strips, speech time, reception tickets) |
| `expire_audio.py` | Run audio retention by hand (the worker scheduler runs it nightly) |
| `restore_drill.py` | Load a database backup into a scratch database and check it; record the result in [`docs/runbook.md`](#doc-docs-runbook-md) |

### Repository layout

| Path | Contents |
| --- | --- |
| [`apps/api`](../apps/api) | FastAPI service: sign-in, users and invites, classes and teachers, uploads, recordings (filters, counts, CSV export, sharing), results, overview, inbox, search, reviews, disputes, re-analysis, live events, rubrics, settings, usage, costs, audit log, erasure |
| [`apps/workers`](../apps/workers) | Celery workers: pipeline stages in `stages/`, outbox relay, notifications, cleanup and the fair GPU scheduler |
| [`apps/web`](../apps/web) | React 18 + TypeScript + Vite app. Design tokens and components are in `src/design/` |
| [`packages/core`](../packages/core) | `sabha_core`: settings, tenant-scoped repository, models, state machine, time mapping, profiles |
| [`packages/asr`](../packages/asr) | `sabha_asr`: providers (Sarvam AI, Gemini, Deepgram, OpenAI, Groq, Qwen, Amazon Transcribe, Whisper), published prices, chunking, batching, speaker roles, colleague-helped calls, the Gemini speaker check and transcript assembly |
| [`packages/llm`](../packages/llm) | `sabha_llm`: the gateway (routing, budgets, retries, cost accounting in `llm_calls`) and PII redaction |
| [`packages/analytics`](../packages/analytics) | `sabha_analytics`: rubric loading, metrics, scoring, grounding and synthesis |
| [`rubrics`](../rubrics) | Versioned rubric files: `<type>.<segment>.v<major>.<minor>.yaml` |
| [`eval`](../eval) | Gold-set tooling and evaluation scripts. The only source of quality numbers |
| [`infra`](../infra) | Docker Compose files, Label Studio for annotators, and Terraform (to come) |
| [`docs`](.) | ADRs, runbook, setup guides, design references, the permission matrix, prompts per week, school guides, rater kit, rubric review sheets, legal drafts ([index](#doc-docs-readme-md)) |
| [`scripts`](../scripts) | Developer helpers (environment check, local bucket setup, synthetic audio) and admin scripts in `scripts/admin/` (see below) |

### Stack

Python 3.12 (uv workspaces, ruff, mypy), FastAPI with Pydantic v2, Celery 5 on Redis 7, MongoDB 7 (PyMongo's async
client in the API, the sync client in workers), S3 via boto3, ffmpeg, Silero VAD, pyannote on CPU for diarisation
(NeMo Sortformer once there is a GPU), Sarvam AI for speech recognition by default, with seven other providers
to choose from ([ADR 0006](#doc-docs-adr-0006-asr-sarvam-md), [ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)), OpenAI `gpt-6-luna` for LLM judgements
([`docs/llm-providers.md`](#doc-docs-llm-providers-md)), PII redaction in `packages/llm` (regular expressions; Presidio was
considered, see P5.2), Langfuse, React 18 with Vite, Tailwind and TanStack Query, and Auth0 over OIDC for sign-in
([ADR 0002](#doc-docs-adr-0002-auth-md)). Infrastructure uses Docker Compose and Terraform. Reasons for
each choice are in [ADR 0001](#doc-docs-adr-0001-repo-and-stack-md).

### Project status

The work follows an 8-week plan, with one Claude Code prompt per task in [`docs/prompts/`](#doc-docs-prompts-readme-md).
Prompt IDs (for example `P2.4`) match the plan and appear in commit messages.

| Area | State |
| --- | --- |
| Monorepo, tooling, local services, settings (P1.1, P0.5) | Done. GitHub Actions removed on 2026-11-02 ([ADR 0010](#doc-docs-adr-0010-no-github-actions-md)); all automated tests removed on 2026-11-19 ([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)) |
| API: errors, request ids, health, rate limits, quotas, permission matrix for every route (P1.4, P7.2, P7.4) | Done |
| Sign-in: Auth0 token checks, web sign-in with PKCE, users, invites, `/v1/me` (P1.5) | Done. The Auth0 tenant itself is set up in week 8; local dev sign-in meanwhile |
  | Tenant-scoped repository, models, indexes (P1.6) | Done |
  | Uploads: presigned multipart, complete, checksum, duplicates (P2.1, P2.2) | Done |
  | Outbox and relay, Celery queues, retries, dead-letter queue, state machine (P2.3, P2.4, P2.5) | Done |
| Preprocess (ffmpeg), silence detection (Silero VAD), diarisation (pyannote, CPU) (P3.2, P3.3, P3.4a) | Done |
| Speech recognition through Sarvam AI, speaker roles, transcript (P3.1, P3.5 to P3.7) | Done |
| LLM gateway, PII redaction, scoring, grounding, synthesis, analyze stage (P5.1, P5.2, P5.4 to P5.7) | Done |
| Reception: ticket, hold metric, not-applicable dimensions, rubric v0.2 (P5.8) | Done. Teaching rubric is v0.1 |
| Sales deal card, team meetings scored as a whole with notes ([ADR 0008](#doc-docs-adr-0008-meetings-md)), company reception (rubric v0.1) | Done as drafts for the owner's review. Demo company "NiaLabs" in the dev seed |
| Support calls for companies: rubric v0.3 (scored on helping the customer), case card (product, problem, steps tried, outcome, follow-up), speaker roles from what each speaker does ([ADR 0011](#doc-docs-adr-0011-evidence-based-speaker-roles-md)) | Done as a draft for the owner's review. On for every company; existing companies were switched on with `scripts/admin/enable_type.py` |
| Sales calls and meetings: rubric v0.4, call or meeting, the client's name, interest level, next actions with dates and priority, coaching for the next call | Done as a draft. Coaching is private to the person analysed for every conversation type |
| Sales rep workspace: Overview, My interactions (one-page summary per call), My next actions (overdue ones under "This week"), private coaching; recording a meeting in the browser | Done (founder's dashboard doc, 2026-11-12) |
| Approved product information: owners and admins add, edit and retire entries in Settings; coaching uses only these; a wrong product statement lowers the score | Done ([ADR 0013](#doc-docs-adr-0013-said-well-and-badly-md)). At most 40 active entries per workspace |
| What the agent said well and badly: a plus and drawback list per call, visible to managers | Done ([ADR 0013](#doc-docs-adr-0013-said-well-and-badly-md)) |
| Pages that answer first: Overview, the conversations list and the report open with one sentence and three cards, people and scores in words, names instead of file names; dark mode | Done (2026-11-12 to 11-13) |
| Speech recognition from more providers: Gemini, Deepgram, OpenAI, Groq, Qwen, Amazon Transcribe, Whisper; model chosen at upload; "Transcribed by" column for owners and admins; transcripts only in English, Hindi and Hinglish | Done ([ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)). Gemini billed and priced by tokens. Upload list since 2026-11-19: Sarvam, OpenAI, Groq (2), Deepgram, Gemini 3.8 Flash, 3.1 Flash-Lite and Flash-Lite, Whisper; Qwen and Amazon Transcribe for comparisons only |
| Number of speakers and the Gemini speaker check, chosen at upload by whoever uploads | Done ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)). Gemini 3.8 Flash, low thinking. Fixed the Roshan call's opening; not yet measured on hand-labelled calls |
| Support calls a colleague helped on: 3 speakers, both agent voices scored as the first agent's | Done ([ADR 0015](#doc-docs-adr-0015-colleague-helped-calls-md)). Per-agent scoring dropped by the owner |
| Comparing speech models on our own calls (`eval/asr_compare.py`) | Done. Run on 3 NiaLabs calls (2026-11-17): Gemini 3.8 Flash, Deepgram Nova-3 and Sarvam shortlisted. Measures difference from Sarvam, not accuracy |
| Read API and web app on real data: recordings, report, upload, people, overview, inbox, search (P5.7b, P6.2, P6.4b, P6.6) | Done |
| UI v2 redesign (`docs/design/v2/`) | Done: tokens, sidebar, Overview, Recordings (tabs with counts, filters by type, class, person, date and score, bulk re-analyse and share, Retry or Close, CSV export) and the report (coaching steps, two-lane timeline with zoom, rubric levels, transcript alongside; pressing a time button again pauses the audio, and a third press carries on), and My progress, the home page for staff (teachers, sales reps, support agents): their own numbers, newest report with the manager's note, the three rubric points to work on, processing and recent recordings. Upload in the same style (type colours and what each is scored on, status dots per file, audio hours for owners and admins, "Upload more"). Reviews as one queue (disputes and paused recordings, filters for disputes, speakers and the rest, "2 of 5 decided") beside the decision: the AI score and its reasoning next to the proposed score, quotes and named times that play, and Accept (no note needed), Keep or Set a different score (note needed); "who is the speaker?" in the same place. The sales report: overall on a Weak to Strong scale with what went well and what to fix first, "Where the points were lost" (rubric points sorted by (5 - score) x weight, the two biggest marked Fix first), the deal at a glance with every quote behind "Show evidence", the agreed next step and talk and listen beside the transcript |
| Sharing a report with the person analysed | Done. Emails them a link and shows the manager's note; it does not change who may see the report (owner's decision, 2026-11-03) |
| Meeting transcripts uploaded instead of audio ([ADR 0009](#doc-docs-adr-0009-transcript-upload-md)) | Done. Google Meet `.txt`; times are approximate, to about a minute |
| Classes and sections (two-level units), teachers with the class-sections they teach | Done (owners and admins) |
| Reviews: queue, "who is the speaker?", resolve ([ADR 0007](#doc-docs-adr-0007-review-outcomes-md)) | Done |
| Disputes: raise, queue, decide, email; the reviewer's score replaces the AI's (P6.7) | Done |
| Re-analysis of one or many recordings, every version kept (P2.8) | Done. Choosing a rubric version is in the API only |
| Live status over server-sent events (P2.6) | Done |
| Settings, rubrics pages, role views (P1.7, P6.8) | Done. Rubric editing waits for calibration |
| Plans and audio-hour allowances, upload pause at the limit, cost in rupees per recording (P6.2, P7.2) | Done. Rate limiter and the 80 % warning email remain |
| Audit log and Activity page, retry or close a failed recording (P1.8, P7.8) | Done. Pause per tenant and usage export remain |
| Audio retention, erasure on request, nightly database export and restore drill (P7.3) | Done locally. Atlas backup and bucket lifecycle come with AWS |
| Status emails (P2.7) | Done, including "report shared" and dispute decisions. Webhooks not wired yet |
| Evaluation tools: gold set, WER, role accuracy, AI-human agreement, grounding, rater kit (P4.1 to P4.6) | Tools done. No real gold set yet, so no quality figures |
| LLM bake-off, calibration, eval gate, speech-model accuracy (WER), NeMo Sortformer on GPU (P5.3, P5.9, P4.7, P3.4b) | Not started. Needs real hand-annotated recordings (and a GPU) |
| Consent records in the app (P6.9) | Parked for the law team. Consent is still required at upload (golden rule 9) |
| AWS staging and production, Terraform, monitoring, Auth0 tenant | Planned for week 8 |

### Running costs

This section lists what Sabha pays for, what has been measured so far and which savings are already built in, so
that cost ideas can be weighed against facts. Every figure below comes from our own stored records (`llm_calls`,
`stage_runs`) or a provider's published price list, with the date. Nothing is estimated (golden rule 6).

#### What costs money

| Item | Paid per | What we know |
| --- | --- | --- |
| LLM: OpenAI `gpt-6-luna` | Token | $0.10 per million input tokens, $0.50 per million output, cached input $0.01, cache writes $0.125 (OpenAI model page, 2026-10-24). Every call is recorded with tokens and cost in `llm_calls` |
| Speech recognition: Sarvam AI REST API (`saaras:v4`), the default | Minute of audio sent | ₹0.49 per minute pay as you go; ₹0.45, ₹0.41 and ₹0.38 on the Pro, Growth and Business plans (sarvam.ai/api-pricing, 2026-10-28; in [`sabha_asr/pricing.py`](../packages/asr/sabha_asr/pricing.py)). Audio goes in chunks of at most 30 s, after silence is removed |
| Speech recognition: other providers | Minute or token of audio | Per hour of audio at ₹96.5 per dollar, from published prices in `sabha_asr/pricing.py`: Deepgram Nova-3 ₹30.11, OpenAI `gpt-transcribe` ₹26.06, Groq Whisper Large v3 ₹10.71, Qwen ₹12.16, Amazon Transcribe (Mumbai) ₹34.74. Gemini is billed by tokens (audio in, text and thinking out), and every call's tokens are stored. Measured: Gemini 3.8 Flash with low thinking about ₹13.3 per hour (174 s of a call, 2026-11-19; its input price doubles from 2027-01-01), Gemini 3.1 Flash-Lite about ₹11.0 (2026-11-18) |
| Gemini speaker check (when chosen at upload) | Token | Gemini 3.8 Flash, low thinking: ₹2.16 for a 12-minute call, about ₹10.8 per audio hour (2026-11-18). Added to the recording's speech-recognition cost |
| Diarisation: pyannote on CPU | Compute time | Open model, no licence fee. The slowest stage by far (see below) |
| Preprocessing and VAD: ffmpeg, Silero | Compute time | Open source, runs on CPU |
| Hosting: AWS `ap-south-1` (S3 with 3 buckets, servers for API, workers, Redis), MongoDB Atlas Mumbai | Month | Not priced yet. Must stay in India (golden rule 12) |
| Sign-in (Auth0), email (Amazon SES), error tracking (Sentry) | Month or usage | Not priced yet |

#### Measured so far

Four test recordings on a developer laptop (WSL, 3 GB RAM, no GPU). These are single runs on test audio, not
averages over real school recordings.

| Recording | LLM calls and cost | Preprocess | Diarisation | Transcription | Analysis |
| --- | --- | --- | --- | --- | --- |
| 3 min lesson, 2026-10-22, `o3-mini` (since shut down) | 4 calls, $0.066 | 11 s | 172 s | 5 s | 70 s |
| 19.8 min lecture, 2026-10-26, `gpt-6-luna` | 4 calls, $0.0068 | 74 s | 1,326 s | 49 s | ended `analysis_failed` |
| 28.2 min lecture, 2026-10-26, `gpt-6-luna` | 4 calls, $0.0066 | 117 s | 1,676 s | 49 s | ended `analysis_failed` |
| 28.2 min lecture, 2026-11-03, `gpt-6-luna` | 6 calls, $0.0097 | about 2 min | about 28 min | 46 s | about 2 min, completed |

What these show:

- **Diarisation on CPU takes about as long as the recording itself**, about 90% of the processing time on the two
  long recordings. It is the main compute cost and the main reason a report takes as long as it does.
- **LLM cost per recording is under one cent with `gpt-6-luna`**, whose token prices are about a tenth of
  `o3-mini`'s. Each
  analysis makes 2 scoring calls (about 10,000 input and 2,000 to 3,000 output tokens each), 1 synthesis call and
  1 segmentation call.
- **The prompt cache did not hit.** The second scoring call repeats the same 10,000-token prefix but recorded
  `cached_tokens: 0` and a cache write instead. With `gpt-6-luna`, a cache write costs more than plain input.
- The 2026-11-03 run cost ₹12.46 in all, from its cost card: speech recognition ₹11.53 (23.5 minutes of speech
  sent, out of 28.2 recorded) and LLM ₹0.94. Speech recognition was about 93% of the cost.
- The October runs predate the cost card, so their Sarvam cost was not recorded. Since 2026-10-28 every recording shows
  an expected cost at upload and its actual cost in rupees when done (speech recognition from Sarvam's published
  price, LLM from `llm_calls`, converted at `USD_INR_RATE` when it is set).

#### Savings already built in

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
  ([ADR 0005](#doc-docs-adr-0005-fairness-md)), so one busy school cannot force extra machines for everyone.

#### Limits on any cost saving

A saving cannot break these: data stays in India; PII is redacted before any LLM call; every judgement cites quotes
that are checked against the transcript; no provider is swapped silently; staff are analysed, never students; and
quality figures come only from evaluation on real, human-rated recordings. The full rules are in
[`CLAUDE.md`](#doc-claude-md).

#### Open questions

- Is a GPU (for diarisation, and later NeMo Sortformer) cheaper per recording hour than CPU, at pilot volume?
- Should diarisation run on a cheaper or spot machine, since reports are not needed in real time?
- Is Gemini 3.8 Flash as accurate as Sarvam? The 2026-11-17 comparison on 3 NiaLabs calls found it differs from
  Sarvam on 26.4% of words, but takes about 90 s per minute of audio. With low thinking it costs about ₹13.3 per
  audio hour against Sarvam's ₹29.40. A hand-corrected gold set is needed before it can become the default.
- Does the Gemini speaker check improve speaker labels on most calls, or only on hard openings like the Roshan
  call's? Needs hand-labelled calls (`eval/roles.py`).
- Would OpenAI's Batch API or a lower reasoning effort cut LLM cost without hurting agreement with raters?
- Why does the prompt cache not hit between the two scoring calls, and is caching worth it with `gpt-6-luna`?
- Audio is kept 90 days by default. How long should artefacts be kept, and when can they move to cheaper S3
  storage classes?
- Expected pilot volume (recordings per school per week, average length) is not set yet, so monthly totals
  cannot be worked out.


### Checks before pushing

There is no CI: pushes to GitHub run nothing ([ADR 0010](#doc-docs-adr-0010-no-github-actions-md)). Run the checks
locally before pushing:

- `make lint`: ruff, mypy, eslint and tsc.
- Try the change in the running app: there are no automated tests ([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)).
- pre-commit runs detect-secrets on every commit.

### Contributing

- **Read [`CLAUDE.md`](#doc-claude-md) first.** It holds the rules, conventions and definition of done.
- **Plan before code** for anything bigger than a small fix. Keep each change to one concern and small enough to
  review in under 15 minutes.
- **Check every change by hand.** There is no test suite ([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)), so
  changes to tenant isolation, grounding, idempotency, the state machine or permissions need a careful check in the
  running app. A new route needs its row in [`docs/security/permissions.yaml`](#doc-docs-security-permissions-yaml).
- **Explain dependencies and decisions.** Say why you are adding any new dependency. Record architecture
  decisions as ADRs in [`docs/adr/`](adr).
- **Put the prompt ID in commit messages,** for example `P2.4: celery queues per stage with DLQ`.
- **Never commit `.env` files, recordings or gold transcripts.** They are gitignored, and pre-commit runs
  detect-secrets.

<a id="doc-docs-readme-md"></a>

## docs

*Source: [`docs/README.md`](README.md)*

Written knowledge for the team and for schools and companies. If someone else would need to know it to operate or
change the system, it belongs here. Updated 19 November 2026.

### Start here

| Document | For |
| --- | --- |
| [`../README.md`](#doc-readme-md) | What Sabha is, how to run it, project status and running costs |
| [`../commands.md`](#doc-commands-md) | Every command to run Sabha by hand on one machine, and troubleshooting |
| [`../CLAUDE.md`](#doc-claude-md) | The rules every change must follow |
| [`documentation.md`](documentation.md) | Every document below in one file, with a table of contents. Rebuild it after editing any doc: `uv run python scripts/build_documentation.py` |
| [`runbook.md`](#doc-docs-runbook-md) | Operating notes: deploying model changes, backups and the restore drill, audio retention, erasure, backfill |

### Decisions (ADRs)

| ADR | Decision |
| --- | --- |
| [0001](#doc-docs-adr-0001-repo-and-stack-md) | Repository layout and technology stack |
| [0002](#doc-docs-adr-0002-auth-md) | Auth0 for sign-in; local sign-in until it is set up |
| [0003](#doc-docs-adr-0003-local-object-storage-md) | RustFS for local object storage |
| [0005](#doc-docs-adr-0005-fairness-md) | Fair scheduling of processing across tenants |
| [0006](#doc-docs-adr-0006-asr-sarvam-md) | Sarvam AI for speech recognition, with approximate word timing |
| [0007](#doc-docs-adr-0007-review-outcomes-md) | How a recording leaves "Needs review" |
| [0008](#doc-docs-adr-0008-meetings-md) | Meetings are analysed as a whole |
| [0009](#doc-docs-adr-0009-transcript-upload-md) | Meeting transcripts can be uploaded instead of audio |
| [0010](#doc-docs-adr-0010-no-github-actions-md) | No GitHub Actions |
| [0011](#doc-docs-adr-0011-evidence-based-speaker-roles-md) | Speaker roles from what each speaker does |
| [0012](#doc-docs-adr-0012-more-asr-providers-md) | More speech-to-text providers, the upload list and Gemini's cost per hour |
| [0013](#doc-docs-adr-0013-said-well-and-badly-md) | What the agent said well and badly, checked against product information |
| [0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md) | Number of speakers and the Gemini speaker check, chosen at upload |
| [0015](#doc-docs-adr-0015-colleague-helped-calls-md) | Support calls a colleague helped on stay the first agent's |
| [0016](#doc-docs-adr-0016-no-automated-tests-md) | Automated tests removed |

### Reference

| Folder or file | Contents |
| --- | --- |
| [`llm-providers.md`](#doc-docs-llm-providers-md) | The LLM provider and model (OpenAI `gpt-6-luna`), prices and the questions asked of OpenAI |
| [`webhooks.md`](#doc-docs-webhooks-md) | Webhook format and signing (sending is not wired yet) |
| [`security/`](security) | `findings.md` (security findings and checks) and `permissions.yaml` (who may call every API route) |
| [`design/`](design) | Design tokens (`tokens.md`) and the v2 page mockups (`v2/`) |
| [`setup/`](setup) | Setting up Auth0 (`auth.md`) and the AWS checklist (`cloud-checklist.md`), both for week 8 |
| [`annotation-guidelines.md`](#doc-docs-annotation-guidelines-md), [`raters/`](raters), [`rubrics/`](rubrics) | Building the gold set: transcript annotation, the rater guide and rubric review sheets |
| [`guides/`](guides) | The recording guide for schools |
| [`legal/drafts/`](legal/drafts) | Drafts of consent forms and notices, waiting for the law team |
| [`prompts/`](prompts) | The 8-week plan, one Claude Code prompt per task (history: kept as written) |

<a id="part-2"></a>

# Part 2. Rules for every change

<a id="doc-claude-md"></a>

## Sabha — Conversation Intelligence Platform

*Source: [`CLAUDE.md`](../CLAUDE.md)*

Sabha turns recorded conversations (lessons, counselling sessions, front-desk calls, meetings, sales calls)
into speaker-labelled transcripts and rubric-based, evidence-backed feedback. One multi-tenant product
serves schools, colleges and companies; an organisation profile changes labels, default rubrics and rules,
never code. The pilot (8 weeks) covers **teaching and reception for schools**.

Read this file fully before any task. If a request conflicts with a rule below, stop and say so.

### Golden rules (never break these)

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

### Stack

| Area | Choice |
| --- | --- |
| Python | 3.12, `uv` workspaces, `ruff`, `mypy --strict` on `packages/` |
| API | FastAPI, Pydantic v2, Uvicorn; async MongoDB via `pymongo.AsyncMongoClient` (PyMongo 4.9+, not Motor) |
| Workers | Celery 5 on Redis 7; sync `pymongo.MongoClient` inside tasks |
| Database | MongoDB 7 replica set (transactions + change streams required, also in tests) |
| Storage | S3 (`ap-south-1`) in staging/prod, RustFS locally (see `docs/adr/0003-local-object-storage.md`); boto3 |
| Audio | ffmpeg/ffprobe, Silero VAD, pyannote or NeMo Sortformer, ASR via `packages/asr` |
| LLM | `packages/llm` gateway (routing, budgets, retries, caching), Langfuse tracing, Presidio redaction |
| Web | React 18 + TypeScript + Vite, Tailwind, TanStack Query, React Router |
| Auth | OIDC with Auth0 (`docs/adr/0002-auth.md`); JWT validated in the API; roles and tenants from our own records |
| Infra | Docker Compose (dev, staging, prod pilot), Terraform for AWS; no CI (ADR 0010) |
| Observability | OpenTelemetry, Prometheus, Grafana, Sentry, structured JSON logs |

### Repo layout

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

### Domain model

Collections: `tenants, units, users, people, recordings, stage_runs, transcripts, rubrics, analyses, scores,
disputes, usage_events, outbox, audit_log`, plus `identities` (login links, ADR 0002), `idempotency_keys`
(create replays, 24 h TTL), `llm_calls` (LLM usage, P5.1), `dlq` (failed pipeline jobs, P2.4), `deliveries` (emails and webhooks sent, P2.7), `product_info` (approved product information for coaching) and `relay_state`. The full list with indexes is `sabha_core/indexes.py`.

Recording status (state machine in `sabha_core/state.py`, the ONLY place transitions are defined):
`CREATED → UPLOADED → PREPROCESSING → DIARIZING → TRANSCRIBING → ANALYZING → COMPLETED`,
plus `FAILED` and `NEEDS_REVIEW` reachable from any worker stage.

Queues: `cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`.

Organisation profiles: `school` (pilot), `college`, `company`. UI words come from the tenant's `labels`
dictionary (`person`, `recording`, `unit`, ...). Never hard-code "Teacher" or "Lesson" in UI strings.

### API conventions

- Versioned paths `/v1/...`; OpenAPI must stay accurate.
- `Idempotency-Key` header on every create; replays return the original response.
- Errors: RFC 9457 `application/problem+json` with a stable `code` and `request_id`.
- Cursor pagination (`?cursor=&limit=`), never offset.
- Times stored in UTC (ISO 8601); the web app displays Asia/Kolkata.
- Every playback, export and score change writes `audit_log`.

### Commands

```
make dev          # docker compose up: mongo (replica set), redis, rustfs, api, workers, web
make lint         # ruff, mypy, eslint, tsc
make eval-wer     # eval/wer.py on the frozen gold set
make eval-kappa   # eval/kappa.py on the calibration hold-out split
```

### How to work in this repo

- **Plan first.** For any task bigger than a small fix, propose a plan (files, functions) and wait for
  approval before writing code.
- **Small diffs.** One concern per change. Keep each PR reviewable in under 15 minutes.
- **No automated tests** (removed by the owner on 2026-11-19, `docs/adr/0016-no-automated-tests.md`). Check each
  change with `make lint` and in the running app; take extra care with critical paths (tenant isolation,
  grounding, idempotency, state machine). Add every new route to `docs/security/permissions.yaml`.
- **No new dependencies without saying why** and noting it in the PR description.
- **Record decisions** that change architecture as an ADR in `docs/adr/NNNN-title.md`.
- **Never** bypass the tenant check or add `# type: ignore` without a reason.
- **When unsure** about a product rule, ask rather than guess.

### Definition of done

Merged to main with `make lint` passing locally and checked in the running app, deployed to staging, visible in the Friday demo, and documented
(README, runbook or ADR) where someone else would need it.

<a id="part-3"></a>

# Part 3. Running Sabha

<a id="doc-commands-md"></a>

## Sabha: every command to run it by hand

*Source: [`commands.md`](../commands.md)*

Copy-paste commands for running Sabha on this machine (WSL 2, Ubuntu, Docker under systemd, repo at `/root/sabha`).
Every command assumes you are in the repo root:

```bash
cd /root/sabha
```

Contents: [Daily quick start](#daily-quick-start) · [First-time setup](#1-first-time-setup-once-per-machine) ·
[Start](#2-start-everything) · [Check](#3-check-that-everything-is-running) · [Logs](#4-logs) ·
[Use the app](#5-use-the-app) · [Stop](#6-stop-everything) · [Restart after code changes](#7-restart-after-changing-code) ·
[Look inside the database](#8-look-inside-the-database-read-only) · [Checks](#9-checks) ·
[Admin scripts](#10-admin-scripts) · [Troubleshooting](#11-troubleshooting) · [Reset](#12-reset-or-wipe-local-data)

---

### Daily quick start

Start everything (services plus the five app processes in the background, logs in `/tmp/sabha-logs`):

```bash
cd /root/sabha
systemctl start docker            # only if Docker is not already running
make dev                          # MongoDB, Redis, RustFS + buckets
mkdir -p /tmp/sabha-logs
nohup make api      > /tmp/sabha-logs/api.log     2>&1 &
nohup make relay    > /tmp/sabha-logs/relay.log   2>&1 &
nohup make workers  > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat     > /tmp/sabha-logs/beat.log    2>&1 &
nohup pnpm -C apps/web dev > /tmp/sabha-logs/web.log 2>&1 &
```

Wait about 15 seconds, then check:

```bash
curl -s http://127.0.0.1:8000/ready; echo
curl -s -o /dev/null -w "web: %{http_code}\n" http://localhost:5180/
```

Open http://localhost:5180 and sign in.

Stop everything at the end of the day:

```bash
pkill -f 'uvicorn sabha_api'; pkill -f 'sabha_workers.relay'; pkill -f 'sabha_workers.worker worker'
pkill -f 'sabha_workers.worker beat'; pkill -f 'apps/web/node_modules/.*vite'
make down
```

---

### 1. First-time setup (once per machine)

#### 1.1 Tools

Check what is installed (this machine has uv 0.13, Node 22.23, pnpm 10.33, Docker 29.1, Compose 2.40):

```bash
uv --version; node --version; pnpm --version; docker --version; docker compose version
```

Install anything missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv (installs to ~/.local/bin; Python 3.12 comes through uv)
corepack enable                                     # pnpm at the version the repo pins
systemctl enable --now docker                       # start Docker now and at every boot
```

#### 1.2 Dependencies, models and `.env`

```bash
make setup          # creates .env (if missing), installs Python + web dependencies, git hooks, VAD model
make setup-speech   # pyannote + CPU PyTorch for diarisation and its model (needs HF_TOKEN in .env first)
```

Models land in `~/.cache/sabha/models/` (`silero_vad-v6.2.3.onnx`, `pyannote-community-1-3533c8cf`). Check:

```bash
ls ~/.cache/sabha/models
```

Edit `.env` (`nano .env`). Every setting is explained in `.env.example`. The ones that matter:

| Setting | Value |
| --- | --- |
| `APP_ENV` | `local` |
| `OPENAI_API_KEY` | Your OpenAI key (analysis; also OpenAI speech recognition) |
| `SARVAM_API_KEY` | Your Sarvam key (speech recognition, the default) |
| `GEMINI_API_KEY` | Your Gemini key: Gemini speech recognition and the Gemini speaker check |
| `DEEPGRAM_API_KEY`, `GROQ_API_KEY` | Optional: Deepgram and Groq Whisper speech recognition. A model without its key shows "not set up" on the upload page |
| `HF_TOKEN` | Hugging Face token (only for `make setup-speech`) |
| `USD_INR_RATE` | Optional: shows LLM cost in rupees |

#### 1.3 Sign-in: choose one

**Option A: username and password (current setup).**

```bash
uv run python scripts/admin/hash_password.py      # type the password twice; prints a hash
```

In `.env`:

```
DEV_LOGIN=false
LOGIN_USERNAME=SysAdmin
LOGIN_PASSWORD_HASH='<the hash printed above>'
LOGIN_AS=owner@demo-school.example
```

In `apps/web/.env.local`:

```
VITE_AUTH_MODE=password
```

**Option B: pick a seeded user from a list (no password).**

In `.env`:

```
DEV_LOGIN=true
OIDC_ISSUER=http://localhost:8000/dev-idp
OIDC_AUDIENCE=sabha-local
OIDC_CLIENT_ID=sabha-web
```

In `apps/web/.env.local`, remove the `VITE_AUTH_MODE=password` line. After changing `.env`, restart the API; after
changing `apps/web/.env.local`, restart the web app.

#### 1.4 Demo data

```bash
make dev                                              # services must be up first
uv run python scripts/admin/dev_seed.py               # Demo School, NiaLabs, users (safe to repeat)
```

---

### 2. Start everything

#### 2.1 Services (Docker)

```bash
systemctl status docker --no-pager | head -3     # "active (running)"? If not: systemctl start docker
make dev
```

Expected at the end: `ok sabha-audio`, `ok sabha-artefacts`, `ok sabha-backups`.

#### 2.2 App processes: option A, one terminal each (easiest to watch)

Open five terminals (in VS Code: Terminal → New Terminal), `cd /root/sabha` in each, then:

| Terminal | Command | Ready when the log shows |
| --- | --- | --- |
| 1 | `make api` | `Application startup complete.` |
| 2 | `make relay` | `outbox relay started` |
| 3 | `make workers` | `celery@<hostname> ready.` |
| 4 | `make beat` | `beat: Starting...` |
| 5 | `pnpm -C apps/web dev` | `Local: http://localhost:5180/` |

#### 2.3 App processes: option B, all in the background

The same as the [daily quick start](#daily-quick-start):

```bash
mkdir -p /tmp/sabha-logs
nohup make api      > /tmp/sabha-logs/api.log     2>&1 &
nohup make relay    > /tmp/sabha-logs/relay.log   2>&1 &
nohup make workers  > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat     > /tmp/sabha-logs/beat.log    2>&1 &
nohup pnpm -C apps/web dev > /tmp/sabha-logs/web.log 2>&1 &
```

What each one does:

- **api**: the backend on http://localhost:8000. It reloads itself when you edit `apps/api` or `packages/core`.
- **relay**: starts the next pipeline stage when one finishes. Without it, uploads sit at "uploaded" forever.
- **workers**: does the processing (preprocess, diarise, transcribe, analyse, emails).
- **beat**: timed jobs (stuck-job sweeper every 5 min, upload cleanup hourly, nightly retention and backup).
- **web**: the website on http://localhost:5180. It reloads itself when you edit `apps/web`.

---

### 3. Check that everything is running

```bash
curl -s http://127.0.0.1:8000/health; echo     # {"status":"ok"}
curl -s http://127.0.0.1:8000/ready; echo      # mongo, redis, storage, indexes: all "ok"
curl -s -o /dev/null -w "web: %{http_code}\n" http://localhost:5180/     # web: 200
uv run python scripts/check_env.py             # validates .env and every service (run while the API is up)
```

Which app processes are running (each should show at least one line):

```bash
for p in 'uvicorn sabha_api' 'sabha_workers.relay' 'sabha_workers.worker worker' 'sabha_workers.worker beat' 'apps/web/node_modules/.*vite'; do
  printf '%-30s %s\n' "$p" "$(pgrep -f "$p" >/dev/null && echo running || echo STOPPED)"
done
```

Docker services:

```bash
docker ps --format '{{.Names}}  {{.Status}}'   # sabha-dev-mongo-1, -redis-1, -rustfs-1: "Up ... (healthy)"
```

Ports in use (MongoDB 27017, Redis 6380, RustFS 9000/9001, API 8000, web 5180):

```bash
ss -ltnp | grep -E ':(27017|6380|9000|9001|8000|5180) '
```

---

### 4. Logs

Background logs (option B):

```bash
tail -f /tmp/sabha-logs/workers.log            # pipeline progress; Ctrl+C to stop watching
tail -f /tmp/sabha-logs/api.log
tail -n 50 /tmp/sabha-logs/relay.log
```

Errors only:

```bash
grep -h -E '"level": "(ERROR|WARNING)"|Traceback' /tmp/sabha-logs/*.log | tail -n 30
```

Docker services (MongoDB, Redis, RustFS):

```bash
make logs                                       # follow all; Ctrl+C to stop
docker logs --tail 50 sabha-dev-mongo-1
```

The logs are JSON lines. For readable output: `tail -f /tmp/sabha-logs/workers.log | grep -o '"message": "[^"]*"'`.

---

### 5. Use the app

| What | Where |
| --- | --- |
| Website | http://localhost:5180 |
| API endpoint list (try requests in the browser) | http://localhost:8000/docs |
| Storage console (RustFS) | http://localhost:9001: username and password are `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` in `.env` |

Show the storage console login:

```bash
grep -E '^\s*S3_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)=' .env
```

**Processing a recording:** sign in → Upload → choose the files → for each, the type and the person (and class) →
tick consent → Upload. For audio you can also set:

- **Number of speakers:** Automatic, or 2 to 10. Support calls start at 2 (one agent, one customer).
- **Telling the speakers apart:** Standard (pyannote), or Standard + Gemini check, which fixes lines given to the
  wrong person and costs about ₹10.8 per audio hour ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)).
- **Support calls: "Did a colleague help on this call?"** Yes asks for 3 speakers; every score still goes to the
  agent ([ADR 0015](#doc-docs-adr-0015-colleague-helped-calls-md)). Anyone but staff can also name the colleague.
- **Transcription model** (owners and admins only): Sarvam is the usual one.

The status moves through uploaded → preprocessing → diarizing → transcribing → analyzing → completed. On this
laptop, diarisation takes about as long as the speech in the recording (a 20-minute lesson: about 20 minutes).

**Retry a failed recording:** open it (Recordings → the failed one) → Retry. Only owners and admins see the button.
It reruns only the stage that failed; earlier stages are not repeated. Retry, don't upload the same file again:
a new upload repeats every stage, including the slow diarisation and the paid speech recognition.

Only upload audio you have consent for. No real school recordings until the providers' data terms are confirmed.

---

### 6. Stop everything

Stop the app processes:

- **Option A (terminals):** Ctrl+C in each of the five terminals.
- **Option B (background):**

```bash
pkill -f 'uvicorn sabha_api'
pkill -f 'sabha_workers.relay'
pkill -f 'sabha_workers.worker worker'
pkill -f 'sabha_workers.worker beat'
pkill -f 'apps/web/node_modules/.*vite'
```

Then the Docker services (your data is kept):

```bash
make down
```

A recording being processed when you stop will continue from its stage on the next start (the stuck-job sweeper
re-sends it after 30 minutes without a heartbeat).

---

### 7. Restart after changing code

The web app reloads by itself. The API reloads by itself only for changes in `apps/api` and `packages/core`; after a
change in `packages/asr`, `packages/llm` or `packages/analytics` (for example the upload page's model list), restart
it too. **The workers, relay and beat never reload**: after any change to `packages/` or `apps/workers/`, or after
`git pull`, restart them. If you skip this, workers run old code, and a
recording can fail the same way on every retry (for example `unexpected_ValidationError ... Extra inputs are not
permitted`).

Background (option B):

```bash
pkill -f 'sabha_workers.worker worker'; pkill -f 'sabha_workers.worker beat'; pkill -f 'sabha_workers.relay'
sleep 3
nohup make workers > /tmp/sabha-logs/workers.log 2>&1 &
nohup make beat    > /tmp/sabha-logs/beat.log    2>&1 &
nohup make relay   > /tmp/sabha-logs/relay.log   2>&1 &
```

Restart the API (background):

```bash
pkill -f 'uvicorn sabha_api'; sleep 2
nohup make api > /tmp/sabha-logs/api.log 2>&1 &
```

Terminals (option A): Ctrl+C in the workers, beat and relay terminals (and the API's, if needed), then run
`make workers`, `make beat` and `make relay` (and `make api`) again.

After `git pull` or a dependency change, first run:

```bash
uv sync && pnpm -C apps/web install
```

After changing `.env`, restart everything: [stop](#6-stop-everything), then [start](#2-start-everything).

---

### 8. Look inside the database (read-only)

Open a MongoDB shell (type `exit` to leave):

```bash
docker exec -it sabha-dev-mongo-1 mongosh sabha
```

Or run one query from your normal shell:

```bash
docker exec sabha-dev-mongo-1 mongosh --quiet sabha --eval '<query>'
```

Useful queries (paste inside `mongosh sabha`):

```js
// The 10 newest recordings with their status
db.recordings.find({}, {file_name: 1, status: 1, status_reason: 1, duration_ms: 1, created_at: 1}).sort({created_at: -1}).limit(10)

// How many recordings are in each status
db.recordings.aggregate([{$group: {_id: {status: "$status", reason: "$status_reason"}, n: {$sum: 1}}}])

// Every stage run of one recording (replace the id): timing, attempts and errors
db.stage_runs.find({recording_id: "<recording id>"}, {stage: 1, attempt: 1, status: 1, duration_ms: 1, error_code: 1, error_detail: 1, meta: 1}).sort({started_at: 1})

// Failed jobs waiting for a retry (dead letters)
db.dlq.find({replayed_at: null}, {recording_id: 1, stage: 1, error_code: 1, error_detail: 1, created_at: 1}).sort({created_at: -1})

// LLM calls and cost for one recording
db.llm_calls.find({recording_id: "<recording id>"}, {task: 1, model: 1, status: 1, error_code: 1, tokens_in: 1, tokens_out: 1, cost_usd: 1, created_at: 1})

// Speech recognition cost per recording (rupees; includes the Gemini speaker check when it ran)
db.transcripts.find({}, {recording_id: 1, asr_model: 1, asr_billed_ms: 1, asr_cost_inr: 1})

// What the Gemini speaker check did (lines asked about, moved, unsure, cost)
db.transcripts.find({speaker_check: {$ne: null}}, {recording_id: 1, speaker_check: 1})

// The choices made at upload for the 10 newest recordings
db.recordings.find({}, {file_name: 1, asr_choice: 1, speaker_count: 1, speaker_model: 1, transferred: 1, transfer_person_id: 1}).sort({created_at: -1}).limit(10)

// Recordings that look stuck (still processing after 1 hour)
db.recordings.find({status: {$in: ["PREPROCESSING", "DIARIZING", "TRANSCRIBING", "ANALYZING"]}, status_changed_at: {$lt: new Date(Date.now() - 3600e3)}}, {status: 1, status_changed_at: 1})
```

Do not edit data by hand in the shell. Use the app or the admin scripts: every document must keep its
`tenant_id`, and changes must go through the audit log.

---

### 9. Checks

There are no automated tests: they were removed on 2026-11-19 ([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)).
Check a change with `make lint` and by trying it in the running app.

| Command | What it does | Needs |
| --- | --- | --- |
| `make lint` | ruff, mypy, eslint, prettier, tsc | Nothing running |
| `make fmt` | Fix formatting and simple lint issues | Nothing running |

Evaluation (needs real, human-annotated data):

```bash
make eval-wer HYP_DIR=<folder of transcript@v1 files>
make eval-kappa RUBRIC=<rubric yaml> AI_DIR=<folder of reports> SCORES="<rater json files>"
```

---

### 10. Admin scripts

```bash
uv run python scripts/admin/dev_seed.py               # demo school, demo company and users (local only; repeatable)
uv run python scripts/admin/hash_password.py          # hash for LOGIN_PASSWORD_HASH

uv run python scripts/admin/create_tenant.py --name "Green Valley School" --profile school --plan pilot \
    --owner-email principal@example.com --owner-name "Asha Rao" --audio-hours 100
uv run python scripts/admin/set_plan.py --tenant <tenant id> --plan starter --audio-hours 100
uv run python scripts/admin/enable_type.py --type support --profile company --dry-run   # switch a conversation type on for existing workspaces

uv run python scripts/admin/backfill.py --dry-run     # see what would be filled in; then run without --dry-run
uv run python scripts/admin/expire_audio.py --dry-run # see what audio retention would delete; then without it
uv run python scripts/admin/restore_drill.py          # restore the latest backup into a scratch database and check it
```

Try speech recognition alone (sends the audio to the provider in `ASR_PROVIDER`, Sarvam by default, and is billed):

```bash
uv run sabha-asr-transcribe <file.wav>                # 16 kHz mono WAV
```

Compare speech models on calls already transcribed (billed per model; report in `eval/reports/asr-compare-<date>/`):

```bash
uv run python eval/asr_compare.py --tenant demo-company --models gemini:gemini-3.8-flash,deepgram:nova-3 --latest 3
```

Each script explains its options at the top of its file, for example `head -30 scripts/admin/set_plan.py`.

---

### 11. Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker is not running | `systemctl start docker` |
| `make dev` hangs or a container is "unhealthy" | A service failed to start | `docker logs sabha-dev-mongo-1` (or `-redis-1`, `-rustfs-1`); then `make down && make dev` |
| `address already in use` on 8000 or 5180 | An old API or web process is still running | `pkill -f 'uvicorn sabha_api'` or `pkill -f 'apps/web/node_modules/.*vite'`, then start again |
| `check_env.py`: OIDC FAIL, connection refused | The API is not running (it is the sign-in issuer locally) | Start `make api`, run the check again |
| `check_env.py`: OIDC FAIL, HTTP 404 | Expected with the username-and-password sign-in (`DEV_LOGIN=false`): the API checks tokens itself and does not serve that address | Nothing to fix. To test sign-in: `curl -s -X POST http://127.0.0.1:8000/auth/login -H 'content-type: application/json' -d '{"username":"x","password":"y"}'` must answer 401, not 404 |
| Sign-in page says the password is wrong | Wrong password, or the hash in `.env` changed | Make a new hash ([1.3](#13-sign-in-choose-one)) and restart the API |
| Recording stays at **Uploaded** | The relay is not running | Start `make relay` |
| Recording stays at **Created** | The upload did not finish in the browser | Upload again; abandoned uploads are cleaned up after 24 h |
| Recording stays at Preprocessing / Diarizing / ... | Workers are not running, or a long diarisation | Check the workers are running ([3](#3-check-that-everything-is-running)) and `tail -f /tmp/sabha-logs/workers.log`; diarisation takes about as long as the speech |
| Failed: `too_short` / `invalid_audio` | The file is too short or cannot be read | Use a longer or a different audio file |
| Failed: `analysis_failed ... model_not_found` | The LLM model in settings no longer exists | Check `LLM_MODEL_SMALL` / `LLM_MODEL_MID` in `.env` (default `openai:gpt-6-luna`), restart workers, then Retry |
| Failed: `analysis_failed ... HTTP 429 credit_balance_exhausted` | The OpenAI account has no credit left | Add credit in the OpenAI billing page, then Retry (nothing before analysis runs again) |
| Failed: `unexpected_ValidationError ... Extra inputs are not permitted` | Workers are running old code | [Restart the workers](#7-restart-after-changing-code), then Retry |
| Failed: `asr_failed` with 403 | The Sarvam key is invalid or out of credit | Fix `SARVAM_API_KEY` in `.env`, restart workers, then Retry |
| Needs review: `unclear_roles` | It could not tell which speaker is the staff member (teacher, agent, rep) | Reviews → open it → choose the speaker |
| Upload page: a model shows "not set up" | Its key is missing from `.env` | Add the key, restart the API and the workers |
| Upload page: a model you expect is missing, or an old one still shows | The API is running old code | Restart the API ([7](#7-restart-after-changing-code)) |
| Failed: `asr_failed` with 404 "no longer available" from Gemini | Google refuses that Gemini model to our account (2.5 Flash and 2.5 Flash-Lite, since 2026-11-18) | Choose another model at upload ([ADR 0012](#doc-docs-adr-0012-more-asr-providers-md), addendum 2026-11-19), then upload again |
| Failed: `speaker_check_failed` (or stuck retrying `speaker_check_unavailable`) | `GEMINI_API_KEY` missing or Gemini failed; no transcript is made without the check that was asked for | Set the key in `.env`, restart workers, then Retry, or upload with "Standard" speaker separation ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)) |
| Worker killed, or WSL freezes during diarisation | Not enough memory | Close other programs; give WSL more memory in `C:\Users\<you>\.wslconfig` (`[wsl2]` then `memory=6GB`), then `wsl --shutdown` from Windows |
| Web page blank or old after `git pull` | Web dependencies changed | `pnpm -C apps/web install`, restart the web app |
| `ModuleNotFoundError` in Python | Python dependencies changed | `uv sync` (and `uv sync --extra speech` for diarisation), then restart |

The exact reason a recording failed:

```bash
docker exec sabha-dev-mongo-1 mongosh --quiet sabha --eval '
db.recordings.find({status: "FAILED"}, {file_name: 1, status_reason: 1, status_changed_at: 1}).sort({status_changed_at: -1}).limit(5).forEach(r => {
  printjson(r);
  db.stage_runs.find({recording_id: r._id, status: "failed"}, {stage: 1, attempt: 1, error_code: 1, error_detail: 1}).sort({started_at: -1}).limit(1).forEach(printjson);
})'
```

---

### 12. Reset or wipe local data

Stop and start the services again, keeping data:

```bash
make down && make dev
```

**Delete all local data** (every recording, user, transcript and stored file in MongoDB, Redis and RustFS). This
cannot be undone:

```bash
make down
docker compose --env-file .env -f infra/docker-compose.dev.yml -p sabha-dev down -v    # -v deletes the data volumes
make dev
uv run python scripts/admin/dev_seed.py                                                # demo data again
```

Remove the background logs:

```bash
rm -rf /tmp/sabha-logs
```

<a id="doc-docs-runbook-md"></a>

## Runbook

*Source: [`docs/runbook.md`](runbook.md)*

Operating notes for whoever deploys or runs Sabha. Add a section when something needs doing the same way twice.

### Deploying a change that adds a field to a stored document

The models in `packages/core/sabha_core/models.py` refuse fields they do not know (`extra="forbid"`), so a typo or a
stray field never slips into the database. The price: a process running older code cannot read a document written by
newer code. Seen on 2026-10-23 when `Recording.confirmed_roles` was added: the API (already updated) saved new
recordings with the field, the worker (still on the old code) failed to load them, and the uploads stayed at
UPLOADED.

So, when a release adds a field to a model:

1. Restart (or deploy) the **workers and the relay first**, then the API. New code reads old documents fine (the new
   field has a default); old code cannot read new ones.
2. If a recording got stuck meanwhile, it stays at its status with no stage running. The stuck-job sweeper
   (`make beat`) sends it again; locally, re-run the stage for it once the worker is updated.

Locally: `make api` reloads itself on every change but `make workers` and `make relay` do not, so restart them after
changing a model.

### Backups, restore drill, audio retention and erasure (P7.3)

**Backups.** Two copies:
1. Atlas continuous backup (turned on with the AWS setup in the last week; the cluster must be in Mumbai).
2. A nightly export by the worker's beat (`sabha.maintenance.backup`) to the backups bucket:
   `mongo/<YYYY-MM-DD>/<collection>.jsonl.gz` plus `manifest.json` (counts and SHA-256). `idempotency_keys` is left
   out (24-hour records). How long exports are kept is the backups bucket's lifecycle rule.

**Restore drill** (monthly, and after any change to the backup job):

    uv run python scripts/admin/restore_drill.py            # latest backup; prints PASSED or FAILED
    uv run python scripts/admin/restore_drill.py --day 2026-10-27 --keep   # keep restore_drill_20261027 to inspect

It restores into a scratch database named `restore_drill_*` (it refuses any other name, so it cannot touch the live
database), checks every collection's count against the manifest and a sample of documents against the file. Write
the date and result here:

| Date | Environment | Backup day | Result | By |
| --- | --- | --- | --- | --- |

**Audio retention.** Nightly (`sabha.maintenance.expire_audio`): audio older than the tenant's `retention_days` (90
by default) is deleted — the original and the working copies; transcripts, scores and reports stay. The report page
then says the audio was deleted. Before the first run on a new environment, and whenever in doubt:

    uv run python scripts/admin/expire_audio.py --dry-run

Change a customer's period with Sabha's admin tooling (owners see it read-only in Settings).

**Erasure on request.** The owner erases a recording (on its page) or a person with all their recordings and their
login (from People, the person's list): Sabha shows the count first and asks for the name. Activity keeps a
`data.erase` entry with the reason and counts. Whole-organisation erasure is not in the app; ask engineering.

**Backfill after an upgrade.** Fields added after recordings were processed (UI v2: the list rows' speaker strips,
speech time on recordings, reception tickets on analyses) are filled in from the files already in storage. It only
touches documents still missing them, so it is safe to run again. Run it once on each environment after deploying the UI v2 changes:

    uv run python scripts/admin/backfill.py --dry-run
    uv run python scripts/admin/backfill.py

### When a speech-to-text model stops working

Providers retire models or refuse them to new accounts without warning. Google refused Gemini 2.5 Flash and 2.5
Flash-Lite to our account on 2026-11-18 (HTTP 404, "no longer available to new users"), and Google retires
Gemini 3.1 Flash-Lite on 2027-05-07. Gemini answering with a model other than the one asked for fails the chunk
instead of being used quietly (golden rule 7).

1. The recording fails with `asr_failed` (or `speaker_check_failed` for the Gemini speaker check). The reason is
   in the recording's last stage run (`commands.md`, troubleshooting).
2. Before offering a replacement, call it once with our key on a short real clip, and record its cost per audio
   hour from the tokens it billed. Do not offer a model only because its price page lists it.
3. Change the upload list (`CHOICES` in `packages/asr/sabha_asr/registry.py`), Gemini's default model
   (`DEFAULT_MODELS`) or the speaker check's model (`MODEL` in `packages/asr/sabha_asr/speaker_check.py`), add its
   price to `pricing.py`, record the change in [ADR 0012](#doc-docs-adr-0012-more-asr-providers-md) or
   [ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md), and restart the API and the workers.
4. Retry the failed recordings.

<a id="part-4"></a>

# Part 4. Components

<a id="doc-apps-api-readme-md"></a>

## apps/api

*Source: [`apps/api/README.md`](../apps/api/README.md)*

The FastAPI service that the web app and integrations talk to. It holds the versioned `/v1` routers, request and response schemas, OIDC token validation, and thin services that call the tenant-scoped repository in `packages/core`. It authorises uploads and records intent but never touches audio bytes: clients upload straight to object storage with presigned multipart URLs. Errors are RFC 9457 problem+json, every create honours `Idempotency-Key`, and pagination is cursor-based.

### Run it

```
make dev    # Mongo, Redis and RustFS
make api    # http://localhost:8000, reloads on save; needs OIDC_* in .env (P1.5)
```

- `GET /health`: the process is up (never checks a dependency).
- `GET /ready`: Mongo, Redis and both storage buckets answer within 2 s, otherwise 503 `not_ready` naming them.
- `GET /v1/meta`: version, git commit (`GIT_SHA`) and environment.
- `/docs`: OpenAPI, served everywhere except production.

Every response carries `X-Request-Id` (yours if it is 1-128 characters of `[A-Za-z0-9._-]`, otherwise a new one);
the same id is in every log line for the request and in every error body. Errors are `application/problem+json`
with a stable `code` (`sabha_api/errors.py`). Logs are JSON on stdout with secrets masked (`sabha_core/logging.py`);
tracing is on when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (`sabha_core/telemetry.py`).

<a id="doc-apps-workers-readme-md"></a>

## apps/workers

*Source: [`apps/workers/README.md`](../apps/workers/README.md)*

The Celery 5 workers that run the processing pipeline on Redis queues (`cpu.preprocess`, `gpu.speech`, `llm.analyze`, `io.notify`, `billing.meter`), the outbox relay (`make relay`) and the scheduler (`make beat`). Each task (preprocess, speech, analyze, notify, meter, relay) is idempotent: it checks for its output artefact at `{tenant_id}/{recording_id}/{stage}@{version}/` before doing work, runs with `acks_late=True`, and moves recordings only through the state machine in `sabha_core/state.py`.

### Preprocess (P3.2, P3.3)

`sabha_workers/stages/preprocess.py` checks the upload, normalises it with ffmpeg and finds the speech with Silero
VAD. It writes `normalised.wav`, `playback.opus`, `compact.wav` (speech only), `segments@v1.json` (the map back to
the original timeline) and `audio.json` under `{tenant}/{recording}/preprocess@{version}/`.

It needs:

- `ffmpeg` and `ffprobe` on the PATH (installed in the worker images; `apt install ffmpeg` on a dev machine);
- the Silero VAD model file. Run `make models` once. It downloads the pinned file (`sabha_workers/stages/vad.py`:
  URL and SHA-256) to `~/.cache/sabha/models/`. The CPU worker image fetches it at build time and sets
  `VAD_MODEL_PATH`. The model is never downloaded while a recording is being processed.

The VAD settings (`VAD_*` in `.env.example`) are unmeasured starting values; tune them on the gold set.

### Diarization (P3.4)

`sabha_workers/stages/diarize.py` runs speaker diarization on `compact.wav` and writes `diarization@v1.json` under
`{tenant}/{recording}/diarize@{version}/`: the turns on the compact timeline and the same turns on the original
recording timeline. The model sits behind `sabha_asr/diarization.py`.

On a dev machine (CPU):

1. Create a free Hugging Face account, accept the conditions of
   [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) and
   [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0), and put a read token in `.env` as
   `HF_TOKEN`.
2. `make setup-speech`: installs pyannote.audio and CPU-only PyTorch (the optional `speech` extra) and fetches the
   pinned model to `~/.cache/sabha/models/`. A later plain `uv sync` or `make setup` removes the extra again; run
   `make setup-speech` after it.

The token is used only to download the model. While a recording is processed, the model loads from the local
folder with the Hugging Face hub offline, and pyannote's own usage telemetry is switched off
(`docs/security/findings.md` #8).

How many speakers are asked for: the number set at upload, else 3 for a support call a colleague helped on, else
the type's default (support: 2), else pyannote decides (`speaker_count` in `diarize.py`; ADR 0014, ADR 0015).

Model attribution: speaker diarization uses
[pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) by
pyannoteAI, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with
[pyannote.audio](https://github.com/pyannote/pyannote-audio) (MIT).

### Transcribe and the transcript (P3.5 to P3.7)

`stages/transcribe.py` sends `compact.wav` in chunks to the speech-to-text model chosen at upload
(`Recording.asr_choice`) or the configured one, and stores each chunk's words (and, for Gemini, the tokens billed).
`stages/transcript.py` then builds `transcript@v1.json` on the original timeline:

1. Speaker roles from what each speaker does (ADR 0011), or, for a support call a colleague helped on, the two agent
   voices and the customer (`sabha_asr/transfer.py`, `transfer@v1.json`; ADR 0015). Unclear roles send the
   recording to review.
2. If the uploader chose it, the Gemini speaker check (`sabha_asr/speaker_check.py`, `speaker_check@v1.json`;
   ADR 0014). It needs `GEMINI_API_KEY`; if Gemini fails the stage fails (`speaker_check_unavailable` is retried,
   `speaker_check_failed` is not).
3. The speech-to-text cost in rupees (by minute, or by tokens for Gemini, plus the speaker check).

### Analyze (P5.4 to P5.8)

`stages/analyze.py` computes the numbers in code (`sabha_analytics.metrics`), asks the LLM through `sabha_llm`
(PII masked first) to judge each rubric point with quotes, keeps only quotes the grounding check finds in the
transcript, and writes the scores, the summary and, for sales and support, the plus and drawback list (ADR 0013).

### Scheduled jobs (`make beat`)

| Task | Every | What it does |
| --- | --- | --- |
| `sabha.maintenance.abort_stale_uploads` | hour | Cancels uploads never completed |
| `sabha.maintenance.requeue_stuck` | 5 minutes | Sends again any stage whose worker died |
| `sabha.maintenance.expire_audio` | day | Deletes audio past the workspace's retention (`docs/runbook.md`) |
| `sabha.maintenance.backup` | day | Exports the database to the backups bucket (`docs/runbook.md`) |

<a id="doc-apps-web-readme-md"></a>

## apps/web

*Source: [`apps/web/README.md`](../apps/web/README.md)*

The React 18 + TypeScript + Vite single-page app used by staff, managers, reviewers, admins and owners of schools and companies. Design tokens and shared components live in `src/design/`; Tailwind is configured from `docs/design/tokens.md` and the v2 mockups are in `docs/design/v2/`. UI words come from the tenant's `labels` dictionary, never hard-coded, and times are shown in Asia/Kolkata. Routes are in `src/app/routes.tsx`, the menu in `src/app/nav.ts`. The transcript view lives in `src/features/transcript/`; its types mirror `packages/asr/sabha_asr/schemas/transcript.v1.schema.json`. Run it with `pnpm -C apps/web dev`.

### Run the whole product locally (dev sign-in)

Until Auth0 is set up (last), the app signs in through the API's local dev sign-in (`sabha_api/auth/dev_idp.py`,
APP_ENV=local only):

1. In the repo's `.env`: `APP_ENV=local`, `DEV_LOGIN=true`, `OIDC_ISSUER=http://localhost:8000/dev-idp`,
   `OIDC_AUDIENCE=sabha-local`, `OIDC_CLIENT_ID=sabha-web`, `CORS_ORIGINS=http://localhost:5180` (storage CORS for
   direct uploads).
2. `make dev` (MongoDB, Redis, RustFS and the buckets), then `uv run python scripts/admin/dev_seed.py` once.
3. `make api`, `make workers`, `make relay` and `make beat` in four terminals (the pipeline needs `make models`, and
   `make setup-speech` for diarization). Every command is in the repo's `commands.md`.
4. In `apps/web/.env.local`: `VITE_AUTH_MODE=dev`; then `pnpm -C apps/web dev` and open http://localhost:5180.
   Pick someone on the sign-in page. Vite forwards `/v1` and `/dev-idp` to the API on port 8000.

Pages (only finished pages are in the menu):

- **Owners, admins, managers and reviewers:** Overview (their home page), the conversations list and each report
  with its transcript and playback, Reviews (disputes and paused recordings in one queue), People, Rubrics, Upload,
  Activity (audit log) and Settings (including approved product information).
- **Staff:** My progress (home), their own conversations and reports, and Upload for themselves.
- **Sales reps:** their own workspace: Overview, My interactions, My next actions and Private coaching.

Upload takes several files, up to 512 MB each. Per file it asks the type, the person, and for audio the number of
speakers and how speakers are told apart (Standard, or Standard plus the Gemini check; ADR 0014). Support calls also
ask whether a colleague helped (ADR 0015). Owners and admins choose the speech-to-text model.

### Audit exceptions

`package.json` → `pnpm.auditConfig.ignoreGhsas` skips advisories that `pnpm audit --audit-level=high` would otherwise fail on. Each one must be listed here with its reason, and removed once a fix exists.

| Advisory                                                                                                                                                                                                                     | Package and path                        | Why it is ignored                                                                                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)                                                                                                                                                     | `braces` via `tailwindcss` → `chokidar` | No patched version exists. It is a build-time dependency of Tailwind 3's file watcher and never ships to browsers; the attack needs untrusted glob patterns, and ours come from our own config. Goes away when we move to Tailwind 4.                                                                     |
| [GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c)                                                                                                                                                     | `undici` 8.x via `jsdom`                | Unit-test DOM only; never ships to browsers. The fix (undici 8.12.2, published 2026-10-15) is younger than our 14-day install rule. **Remove on or after 2026-10-29** and update undici.                                                                                                                  |
| [GHSA-4w7w-5xrc-9h26](https://github.com/advisories/GHSA-4w7w-5xrc-9h26), [GHSA-2m5v-pch6-74hx](https://github.com/advisories/GHSA-2m5v-pch6-74hx), [GHSA-qrxm-fqhp-jwvm](https://github.com/advisories/GHSA-qrxm-fqhp-jwvm) | `undici` 8.x via `jsdom`                | Same package and fix as the row above (undici 8.12.2; jsdom 30.1.3 asks for it), published 2026-10-15, younger than the 14-day install rule. Unit-test DOM only; tests make no TLS connections to untrusted servers. **Remove on or after 2026-10-29** (from about 15:05 UTC) and update jsdom to 30.1.3. |

<a id="doc-packages-core-readme-md"></a>

## packages/core

*Source: [`packages/core/README.md`](../packages/core/README.md)*

`sabha_core`, the shared foundation every Python app imports: validated settings from environment variables, the tenant-scoped MongoDB repository (the only way to read or write data; a query without `tenant_id` raises), domain models, the recording state machine, object-storage helpers, structured logging and telemetry setup.

<a id="doc-packages-asr-readme-md"></a>

## packages/asr

*Source: [`packages/asr/README.md`](../packages/asr/README.md)*

`sabha_asr`, the multi-provider speech-recognition layer, plus diarisation, speaker roles and transcript assembly.
Configuration picks one active provider per deployment, and owners and admins may choose another model per upload.
Any fallback must be configured explicitly and is logged with its reason, never applied silently (golden rule 7).
Decision records: [ADR 0006](#doc-docs-adr-0006-asr-sarvam-md) (Sarvam), [ADR 0012](#doc-docs-adr-0012-more-asr-providers-md)
(other providers), [ADR 0011](#doc-docs-adr-0011-evidence-based-speaker-roles-md) (roles),
[ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md) (speaker check),
[ADR 0015](#doc-docs-adr-0015-colleague-helped-calls-md) (colleague-helped calls).

| Module | What it does |
| --- | --- |
| `provider.py` | The `AsrProvider` interface, its output (`ChunkResult`: words, language spans, tokens billed), `TokenUsage`, `ProviderError`, and `spread_words` for providers that time phrases only |
| `transcriber.py` | Runs the chosen provider and, only if configured, its fallbacks; records which provider answered, why, and the real-time factor |
| `registry.py` | Builds the transcriber from `ASR_PROVIDER` / `ASR_MODEL` / `ASR_FALLBACKS`; `CHOICES` is the upload page's model list |
| `pricing.py` | Published prices: per minute (`PRICES`) and per token (`TOKEN_PRICES`, Gemini), with source and date |
| `providers/` | `sarvam`, `gemini`, `deepgram`, `openai`, `groq`, `qwen`, `aws`, `whisper` (self-hosted), and `fake` (tests and local only, refused in staging and production) |
| `chunking.py`, `batcher.py` | Chunk planning at VAD joins with overlap and de-duplication; the request batcher (P3.5) |
| `diarization.py` | pyannote behind one interface; asked for an exact number of speakers when one is known |
| `words.py`, `roles.py`, `role_evidence.py` | Words and turns; speaker roles from what each speaker does |
| `transfer.py` | Support calls a colleague helped on: the two agent voices, the customer and the handover point |
| `speaker_check.py` | The Gemini speaker check: lines, the question per 3-minute window, and moving lines between speakers |
| `assembly.py`, `imported.py` | transcript@v1 on the original timeline; transcripts uploaded as text (ADR 0009) |

### On the upload page

Sarvam Saaras v4, OpenAI Transcribe, Whisper Large v3 and Whisper Turbo (Groq), Deepgram Nova-3, Gemini 3.8 Flash,
Gemini 3.1 Flash-Lite, Gemini Flash-Lite and Whisper (own server). A model whose key is missing shows "not set up".
Qwen and Amazon Transcribe are left off (2026-11-19) but still work with `ASR_PROVIDER` and in
`eval/asr_compare.py`. Gemini 2.5 Flash and 2.5 Flash-Lite cannot be used: Google refuses them to our account.

### Settings

`ASR_PROVIDER`, `ASR_MODEL`, `ASR_FALLBACKS`, `ASR_LANGUAGE`, and each provider's key: `SARVAM_API_KEY`,
`GEMINI_API_KEY` (also needed for the speaker check), `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`,
`DASHSCOPE_API_KEY` (Qwen), `AWS_TRANSCRIBE_*`. See `.env.example`.

### Trying a provider by hand

```
ffmpeg -i sample.m4a -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
uv run sabha-asr-transcribe sample.wav > words.jsonl
```

Use only audio you may send to the provider: real recordings need consent, and Gemini, Deepgram,
OpenAI, Groq and Qwen are outside India (ADR 0012).

### Adding a provider

Write an adapter that satisfies `AsrProvider` in `providers/`, add a factory to `registry.PROVIDERS`
and its default model to `DEFAULT_MODELS`, its price to `pricing.py` (with the source and the date checked), and, to
offer it at upload, a row in `registry.CHOICES`. Try it on a real call with `eval/asr_compare.py` before offering it.

<a id="doc-packages-llm-readme-md"></a>

## packages/llm

*Source: [`packages/llm/README.md`](../packages/llm/README.md)*

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

<a id="doc-packages-analytics-readme-md"></a>

## packages/analytics

*Source: [`packages/analytics/README.md`](../packages/analytics/README.md)*

`sabha_analytics`, which turns transcripts into feedback: it loads rubric files, computes metrics in code (talk share, question counts, pace, silence, monologue length), asks the LLM only for judgements, verifies every quoted piece of evidence against the transcript, and assembles the report. Unverified output is never shown to users.

<a id="doc-rubrics-readme-md"></a>

## rubrics

*Source: [`rubrics/README.md`](../rubrics/README.md)*

Rubric definitions as versioned YAML files named `<type>.<segment>.v<major>.<minor>.yaml` (for example `teaching.school.v0.1.yaml`). Each rubric lists weighted dimensions with observable 1–5 anchors, the computed metrics it shows, the report sections it produces, and the inter-rater agreement (Cohen's kappa) the rubric must reach before its scores are shown to users. Changing a rubric means publishing a new version, never editing one in place.

<a id="doc-infra-readme-md"></a>

## infra

*Source: [`infra/README.md`](../infra/README.md)*

Everything needed to run Sabha outside a developer's editor: Docker Compose files for dev, staging and the production pilot, Terraform for AWS in `ap-south-1`, load-test scripts, Grafana dashboards, and the Label Studio setup for annotators. All cloud resources stay in India.

<a id="doc-infra-annotation-readme-md"></a>

## Label Studio for gold transcripts (plan task P4.1)

*Source: [`infra/annotation/README.md`](../infra/annotation/README.md)*

Human annotators use this Label Studio instance to mark who speaks when in pilot recordings and type
exactly what was said. The results become the gold set in `eval/goldset/gold/`, the only source of WER
and speaker-role numbers (CLAUDE.md rule 6).

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Label Studio 1.23.2, localhost only, own login, analytics off, audio mounted read-only |
| `.env.example` | Settings to copy into `.env` (gitignored): admin account, audio folder, bind address |
| `transcript_config.xml` | The labelling interface: waveform, speaker labels, one transcript box per region |
| `../../eval/goldset/import_tasks.py` | Creates tasks from a manifest CSV; refuses rows without `consent_ref` |
| `../../eval/goldset/export_gold.py` | Turns finished annotations into `eval/goldset/gold/<recording>.json` |
| `../../docs/annotation-guidelines.md` | The rules annotators follow |

### Decisions

- **Label Studio's own login, no basic-auth proxy in front.** Sign-up works only through the
  organisation's invite link (`LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK=true`), and the first admin is
  created from `.env`. We decided against an HTTP basic-auth proxy: basic auth uses the `Authorization`
  header, and so does the Label Studio API (`Authorization: Token <key>` for legacy tokens,
  `Authorization: Bearer <access token>` for personal access tokens). With a proxy in front, the import
  and export scripts (and the Label Studio SDK) would have no header left for their token.
- **Localhost only by default.** Ports are published on `127.0.0.1:8080`. Label Studio serves plain
  HTTP. Annotators on other machines should use an SSH tunnel
  (`ssh -N -L 8080:127.0.0.1:8080 <host>`, then open http://localhost:8080). If the team needs a
  shared URL instead, put an HTTPS reverse proxy (TLS only, no basic auth) on the same host and only
  then change `ANNOTATION_BIND_ADDR`. If this ever runs on a cloud machine, it must be in AWS
  `ap-south-1` (CLAUDE.md rule 12).
- **No telemetry.** Usage analytics (`COLLECT_ANALYTICS`), Sentry error reports to HumanSignal
  (`SENTRY_DSN`, `FRONTEND_SENTRY_DSN`) and the PyPI version check (`LATEST_VERSION_CHECK`) are off.
  Each setting is cited in `docker-compose.yml`.
- **Audio is never uploaded.** The recordings folder is mounted read-only and served through Label
  Studio's local-files serving (`/data/local-files/?d=audio/<file>`). Don't use Label Studio's upload
  button for recordings: uploads are copied into Label Studio's own storage.
- **Named volume for Label Studio's data** (`sabha-annotation-label-studio-data`, mounted at
  `/label-studio/data`: SQLite database, generated secret key, exports). The image runs as UID 1001,
  and Docker gives a new named volume the right owner, while a `./data` bind mount would need a manual
  `chown` first. It also keeps real annotations out of the repository folder.
- **Image pinned** to `heartexlabs/label-studio:1.23.2` plus its digest. 1.23.2 (published 2026-09-29)
  was the newest stable release at least two weeks old when this was set up; it is a security patch
  release that also fixes access checks for local-files storage, which we rely on. To upgrade, pick a
  newer stable tag, update tag and digest together, and re-check every setting against that version.
- **SQLite**, the image default, is enough for a small annotation team on one machine. Move to the
  PostgreSQL setup in upstream's own `docker-compose.yml` if it becomes a bottleneck.
- **Everyone sees every project.** In Label Studio Community Edition all users have the same
  permissions and can see all projects (upstream docs, "Add users"). Invite only people who may hear
  every recording in this instance, and run one instance for the gold set only.

### 0. Before you start

- Docker with the Compose plugin (`docker compose version`).
- Only recordings with consent. `import_tasks.py` refuses any row without a `consent_ref`, but the
  audio folder itself is visible to Label Studio, so put nothing else in it.
- The container user (UID 1001) must be able to read the audio: files readable by others and folders
  enterable by others, for example `chmod -R o+rX <audio folder>`.

### 1. Start

```bash
cd infra/annotation
cp .env.example .env
chmod 600 .env
# edit .env: LABEL_STUDIO_USERNAME (an email), LABEL_STUDIO_PASSWORD, ANNOTATION_AUDIO_DIR
docker compose up -d
docker compose ps            # wait until the service is "healthy"
docker compose logs -f label-studio
```

Open http://localhost:8080 (or the port you set in `ANNOTATION_PORT`). Compose refuses to start if the
username, password or audio folder is missing.

Stop with `docker compose down`. That keeps the data volume; `docker compose down -v` deletes it and
every annotation in it. Back it up first:

```bash
docker run --rm -v sabha-annotation-label-studio-data:/data:ro -v "$PWD":/backup alpine:3.20 \
  tar czf /backup/label-studio-data-$(date +%F).tgz -C /data .
```

The backup contains real annotations: keep it off the repository and on encrypted storage in India.

### 2. Admin account and annotators

The admin account is created from `LABEL_STUDIO_USERNAME` / `LABEL_STUDIO_PASSWORD` on the first start;
log in with them. Those values are only used to create the account: editing `.env` later does not
change the password. Change it in the UI (**Account & Settings**) or reset it with
`docker compose exec label-studio label-studio reset_password --username <email>`.

To add annotators: menu at the top left, **Organization**, **Add Members**, copy the invite link and
send it to each person directly. After onboarding, use **Reset Link** so the old link stops working.
The sign-up page refuses anyone without the link.

### 3. Get an API token

The import and export scripts need a token for the admin (or another) account.

1. **Account & Settings** (user icon, top right) > **Personal Access Token** > create one. It is shown once.
2. Keep it in your shell only, never in a file in the repository:

   ```bash
   read -rs LABEL_STUDIO_API_KEY && export LABEL_STUDIO_API_KEY   # paste, Enter
   export LABEL_STUDIO_URL=http://localhost:8080
   ```

A personal access token is a JWT refresh token: the scripts exchange it at `/api/token/refresh/` for a
short-lived access token and send `Authorization: Bearer <access token>`. Legacy tokens
(`Authorization: Token <key>`) also work with the scripts, but they never expire and new organisations
have them switched off (**Organization** > **Settings** > **Access Token Settings**); keep them off.
Revoke a personal access token on the same page when it is no longer needed.

For the `curl` calls below, get an access token first:

```bash
ACCESS=$(curl -s -X POST "$LABEL_STUDIO_URL/api/token/refresh/" -H 'Content-Type: application/json' \
  -d "{\"refresh\": \"$LABEL_STUDIO_API_KEY\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access"])')
```

### 4. Create the project from `transcript_config.xml`

In the UI: **Create Project**, give it a name (for example "Gold transcripts, batch 1"), open
**Labeling Setup**, choose **Custom template**, switch to **Code**, paste the whole of
`transcript_config.xml`, then **Save**. The project id is the number in the project's URL
(`/projects/<id>/`).

Or with the API (from `infra/annotation`):

```bash
python3 -c 'import json; print(json.dumps({"title": "Gold transcripts, batch 1",
  "label_config": open("transcript_config.xml", encoding="utf-8").read()}))' \
| curl -s -X POST "$LABEL_STUDIO_URL/api/projects/" -H "Authorization: Bearer $ACCESS" \
    -H 'Content-Type: application/json' --data-binary @- \
| python3 -c 'import json,sys; print("project id:", json.load(sys.stdin)["id"])'
```

Keep the tag names (`audio`, `speaker`, `transcript`) and label values unchanged: `export_gold.py`
depends on them (`eval/goldset/goldset_common.py`, checked by `eval/goldset/tests/test_transcript_config.py`).

### 5. Connect the audio folder (once per project)

Label Studio only plays a local file if the project has a Local Files storage that contains it.

Project **Settings** > **Cloud Storage** > **Add Source Storage** > **Local Files**:

- Storage title: `Sabha audio (read-only)`
- Absolute local path: `/label-studio/files/audio`
- **Test connection**
- Import method: **Tasks**; file name filter: empty
- Click **Save**, not **Save & Sync**. Syncing would create one task per audio file, without the
  consent and metadata checks. Tasks come only from `import_tasks.py`.

`import_tasks.py` refuses to import into a project that does not have this storage.

### 6. Import recordings

Write a manifest CSV (see `eval/goldset/README.md`), with `file` relative to `ANNOTATION_AUDIO_DIR`:

```bash
python3 eval/goldset/import_tasks.py --manifest path/to/manifest.csv \
  --audio-dir /path/to/ANNOTATION_AUDIO_DIR --dry-run          # check first, contacts nothing
python3 eval/goldset/import_tasks.py --manifest path/to/manifest.csv \
  --audio-dir /path/to/ANNOTATION_AUDIO_DIR --project <id>
```

If any row is refused (no `consent_ref`, missing file, unknown type or language mix, ...), nothing is
imported. Rows already in the project are skipped, so re-running after adding rows is safe.

### 7. Annotate

Annotators follow `docs/annotation-guidelines.md`; the short version is on screen above the waveform.
Keep one annotation per task (the project default). A reviewer corrects that annotation in place and
clicks **Update**, rather than adding a second annotation. `export_gold.py` refuses tasks with more
than one finished annotation unless exactly one is marked ground truth.

### 8. Export gold transcripts

From the API (nothing written to disk except the gold files):

```bash
python3 eval/goldset/export_gold.py --project <id>
```

Or from a file: project > **Export** > **JSON**, save it under `eval/goldset/exports/` (gitignored),
then:

```bash
python3 eval/goldset/export_gold.py --input eval/goldset/exports/<file>.json
```

Output goes to `eval/goldset/gold/<recording_id>.json` (gitignored: it is real data). Tasks without a
finished annotation are skipped; tasks without `consent_ref` or with labelling mistakes are refused
with the region time, so they can be fixed in Label Studio and exported again. Existing gold files are
kept unless you pass `--overwrite`. Delete exported JSON files from `eval/goldset/exports/` when done.

### What has not been tested

Docker was not available when this was written. `docker compose config` (Compose v5.5.1) accepted the
file, `transcript_config.xml` passed Label Studio 1.23.2's own config validation (run offline), and the
scripts were tested against a synthetic export. Not yet tried against a running Label Studio: start-up,
admin creation, sign-up lock, audio playback through local-files serving, the healthcheck, and the
scripts' API calls (token refresh, storage check, import, export). Do that once on the first real
machine and note the result here.

<a id="doc-eval-readme-md"></a>

## eval

*Source: [`eval/README.md`](../eval/README.md)*

Quality evaluation on real, human-annotated data: gold-set manifests and transcripts, word error rate and speaker-role scoring (`wer.py`, `roles.py`), rater agreement (`kappa.py`), grounding checks, the LLM bake-off, and generated reports in `reports/`. Every quality number the product quotes must come from a script here run on the frozen gold set; nothing is estimated by hand.

### Comparing speech-to-text models (`asr_compare.py`, ADR 0012)

Sends the same audio pieces of calls already transcribed with Sarvam to other models, and writes a side-by-side HTML
report with cost, speed and how much each model differs from Sarvam. Sarvam is not asked again (its saved answer is
used), and every model's answers are cached in the report folder, so a second run costs nothing.

```bash
uv run python eval/asr_compare.py --tenant demo-company --models openai,qwen,aws --latest 5
uv run python eval/asr_compare.py --tenant demo-company --models openai:gpt-4o-mini-transcribe --recordings ID,ID
```

Keys come from `.env`: `OPENAI_API_KEY` (openai), `DASHSCOPE_API_KEY` (qwen), `AWS_TRANSCRIBE_BUCKET` plus AWS
credentials (aws). Self-hosted Whisper needs `uv sync --inexact --extra whisper`. `ASR_LANGUAGE=hi-IN` in front of the
command sends a Hindi hint to every model. The report goes to `eval/reports/asr-compare-<date>/index.html` and is not
committed (it holds transcripts).

"Differs from Sarvam" is not accuracy: nobody checked these transcripts by hand. Listen to the highlighted moments to
judge which model is right; word error rate comes only from `wer.py` on the gold set.

<a id="doc-eval-goldset-readme-md"></a>

## eval/goldset

*Source: [`eval/goldset/README.md`](../eval/goldset/README.md)*

Tests (until P1.1 adds eval to the uv workspace): `cd /root/sabha && ~/.local/bin/uv run --no-project --python 3.12 --with pytest --with jsonschema pytest eval/goldset/tests -q`


Tooling for the human-annotated gold set (plan task P4.1). Label Studio setup and the full workflow:
`infra/annotation/README.md`. Rules for annotators: `docs/annotation-guidelines.md`.

| File | Purpose |
| --- | --- |
| `import_tasks.py` | Manifest CSV + audio folder -> Label Studio tasks. Refuses rows without `consent_ref`. |
| `export_gold.py` | Label Studio JSON export -> `gold/<recording_id>.json`. |
| `transcript.schema.json` | Canonical gold transcript schema (JSON Schema draft 2020-12). |
| `goldset_common.py` | Shared vocabulary (types, language mixes, speaker roles, tag names) and a small urllib client. |
| `gold/` | Output. Gitignored: gold transcripts of pilot recordings are real data. |
| `exports/` | Put downloaded Label Studio exports here if you use `--input`. Gitignored; delete after use. |

Both scripts use only the Python standard library and run with any Python 3.12:
`python3 eval/goldset/import_tasks.py --help`. They read the Label Studio URL and token from
`LABEL_STUDIO_URL` and `LABEL_STUDIO_API_KEY` (or `--url` / `--token`; prefer the environment so the
token stays out of shell history). The token is never printed.

### Manifest CSV

Exactly these columns, in any order, UTF-8 (a spreadsheet BOM is fine):

| Column | Rule |
| --- | --- |
| `file` | Path relative to the audio folder, `/` separators, no `..`. Audio extension (`.wav .mp3 .m4a .ogg .opus .flac .webm`). The file name without extension becomes the recording id, so it may only use letters, digits, `.`, `_`, `-`, and must be unique in the manifest and the project. |
| `tenant` | Tenant id (letters, digits, `.`, `_`, `-`). |
| `type` | `teaching` or `reception` (the pilot types; the labelling interface has speaker labels only for these). |
| `language_mix` | `english`, `hindi` or `hinglish`. |
| `room_type` | Lowercase word such as `classroom`, `lab`, `front_desk`, `phone`. No fixed list yet. |
| `consent_ref` | Reference to the consent record. Required: rows without it are refused. |

Example (fictional):

```csv
file,tenant,type,language_mix,room_type,consent_ref
demo-school/demo-teaching-001.wav,demo-school,teaching,hinglish,classroom,CONSENT-DEMO-0001
demo-school/demo-reception-001.mp3,demo-school,reception,english,front_desk,CONSENT-DEMO-0002
```

Values are trimmed; `type`, `language_mix` and `room_type` are lowercased.

**All or nothing.** If any row is refused, every problem in every refused row is printed and nothing is
imported (exit code 1). A partly imported manifest is easy to miss and the missing recordings would
quietly drop out of the gold set; fixing the CSV and re-running is cheap. Tasks whose audio is already
in the project are skipped, so re-running is safe. `--dry-run` validates and prints the tasks without
contacting Label Studio.

### Gold transcript

`gold/<recording_id>.json`, valid against `transcript.schema.json`:

```json
{
  "recording_id": "demo-teaching-001",
  "tenant": "demo-school",
  "type": "teaching",
  "language_mix": "hinglish",
  "consent_ref": "CONSENT-DEMO-0001",
  "source": {"annotator": "ls-user-3", "annotation_id": 502, "exported_at": "2026-10-14T06:00:00Z"},
  "segments": [
    {"speaker_role": "teacher", "start_ms": 512, "end_ms": 6000, "text": "अच्छा, so आज हम photosynthesis पढ़ेंगे"},
    {"speaker_role": "silence", "start_ms": 12500, "end_ms": 15001, "text": ""}
  ]
}
```

- `speaker_role`: `teacher`, `students`, `receptionist`, `caller`, `other`, `silence`.
- Times are integer milliseconds on the original recording: Label Studio's seconds x 1000, rounded half
  away from zero on the decimal value Label Studio stored (`1.0005 s` -> `1001`).
- `start_ms < end_ms`; segments sorted by start (then end, then role); speakers may overlap.
- `text` is empty for `silence` and only for `silence`. Text is kept verbatim apart from Unicode NFC
  and collapsing runs of whitespace into one space.
- `source.annotator` is the Label Studio user id, never a name or email. `exported_at` is UTC.

`export_gold.py` checks its output with a hand-written mirror of the schema (plus the ordering and
`start_ms < end_ms` rules the schema cannot express), so it needs no third-party package; the tests
validate the same output with `jsonschema`. Exit codes: 0 ok (skipped tasks allowed), 1 some task
refused (valid ones are still written), 2 bad input, 3 Label Studio API error.

<a id="part-5"></a>

# Part 5. Decisions (ADRs)

<a id="doc-docs-adr-0001-repo-and-stack-md"></a>

## ADR 0001: Repository layout and technology stack

*Source: [`docs/adr/0001-repo-and-stack.md`](adr/0001-repo-and-stack.md)*

- **Status:** Proposed
- **Date:** 2026-10-14
- **Plan task:** 0.2

### Context

Sabha turns recorded conversations into speaker-labelled transcripts and rubric-based, evidence-backed
feedback for schools, colleges and companies. The 8-week pilot covers teaching and reception for schools.
The system must keep data in India, isolate tenants strictly, run a GPU speech pipeline and an LLM scoring
stage reliably, and be small enough for one team to operate.

Correction (2026-10-17): an earlier version said speech recognition would be ported from a "Lecture Intelligence
System (LIS)". No such codebase exists; `packages/asr` is built here.

### Decision

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

#### Web versions fixed by the Week 0 spike

| Package | Version | Why this one |
| --- | --- | --- |
| React | 18.3.1 | The stack says React 18; current Vite templates default to 19. |
| Tailwind CSS | 3.4.19 | Plan tasks 0.2 and 6.1 expect a `tailwind.config.ts`; Tailwind 4 moves configuration into CSS. Revisit after the pilot. |
| TypeScript | 5.9.3 | TypeScript 7 is the new native compiler; lint tooling added in P1.1 may not support it yet. |
| Vite | 8.3.1 | Current major release. |
| Instrument Sans | `@fontsource/instrument-sans` 5.3.0 | Self-hosted, so pages make no requests to an outside font service (golden rule 12). |
| Package manager | pnpm 10 | As in `CLAUDE.md` commands. |

### Consequences

- One repository means one CI pipeline, one review flow and atomic changes across API, workers and web.
- Shared Python logic in `packages/` must stay free of app-specific imports; `mypy --strict` there enforces
  typed interfaces between apps.
- MongoDB must run as a replica set everywhere, including local dev and tests, which makes Docker a hard
  requirement for development.
- Choosing AWS `ap-south-1` and Atlas Mumbai keeps data in India; any service hosted elsewhere (for example an
  LLM provider or SaaS monitoring) needs an explicit decision before it is added.
- Pinning React 18 and Tailwind 3 trades newer features for stability during the pilot; upgrading either is a
  separate, later change.

<a id="doc-docs-adr-0002-auth-md"></a>

## ADR 0002: Identity provider for login

*Source: [`docs/adr/0002-auth.md`](adr/0002-auth.md)*

- **Status:** Accepted
- **Date:** 2026-10-16
- **Plan task:** 1.5

### Context

Sabha validates OIDC access tokens in the API (ADR 0001) and needs Google login for pilot staff. Users are invited by a
tenant owner or admin; the identity provider only proves who someone is. Roles, tenant and units live in our `users`
collection, not in the provider. Golden rule 12 keeps data in India, and the provider stores staff names and emails.

### Comparison

| | Auth0 (hosted) | Keycloak (self-hosted) |
| --- | --- | --- |
| Where staff data lives | Auth0's public-cloud region; an India region is not offered there as far as we know (to confirm with Auth0) | Our own server in `ap-south-1`, next to MongoDB |
| Running it | Nothing to run; Auth0 patches and scales it | One more container plus a PostgreSQL database to run, patch, back up and monitor |
| Google login | Built-in social connection | Identity brokering to Google; a few console steps |
| Cost | Free tier, then per active user (plan limits to confirm) | No licence fee; we pay for the server and the database |
| Lock-in | Proprietary; migrating users means exporting them | Apache-2.0, open source; export realms as JSON |
| Local development | Uses the hosted dev tenant (needs internet) | Runs in `docker compose`; uses RAM on the 3 GB dev VM |
| SPA and API | Standard OIDC (PKCE, JWKS) | Standard OIDC (PKCE, JWKS) |

### Recommendation

Keycloak, mainly because of golden rule 12: it would keep staff identities in `ap-south-1` without an exception. The
cost is more operations work for a solo engineer: one more service and a PostgreSQL database. Auth0 is less work to run.

### Decision

**Auth0**, chosen by the owner on 2026-10-16. The owner was told that staff names and emails would likely be stored
outside India, and accepted it. This is the golden rule 12 sign-off for this one service. Record the tenant region
here once the tenant exists. Recordings, transcripts and analyses stay in India: Auth0 never sees them.

The code stays provider-neutral, so moving to Keycloak later means changing settings and migrating users:

- The API reads standard claims only (`iss`, `sub`, `aud`, `exp`) and finds the signing keys through OIDC discovery
  (`sabha_api/auth/oidc.py`).
- The web app uses oidc-client-ts with react-oidc-context, not the Auth0 SDK (`apps/web/src/auth/`).
- Roles, tenant and units never come from token claims. Login looks up an `identities` system collection that maps
  (issuer, subject) and an invited email to (tenant, user). It is the one cross-tenant lookup besides `tenants` and
  `outbox`, and only auth code may read it (P1.6 enforces this with a lint test).

### Consequences

- One Auth0 tenant per environment; console steps in `docs/setup/auth.md`.
- People cannot sign themselves up for Sabha. A valid Google login without an invite gets 403 `not_invited`.
- Access tokens are short-lived; the web app renews them with rotating refresh tokens (`offline_access`), so no
  hidden iframe or third-party cookies are needed. Tokens live in the browser's session storage.
- If Auth0 is unreachable, the API keeps using cached signing keys; with none cached it answers 503
  `auth_unavailable`, not 401, so clients don't sign people out during a provider outage.
- New dependencies: PyJWT (with `cryptography`) and httpx in the API; oidc-client-ts and react-oidc-context in the web
  app.

### Addendum (2026-10-28): local password sign-in

For manual testing on a developer machine the owner asked for a username and password kept in `.env`
(`LOGIN_USERNAME`, `LOGIN_PASSWORD_HASH`, `LOGIN_AS`). It is a second door on the local dev sign-in
(`sabha_api/auth/dev_idp.py`), with the same limits:

- `APP_ENV=local` only; settings refuse it anywhere else, and refuse it together with `DEV_LOGIN`, whose
  "Sign in as..." list would skip the password.
- One username. It signs in as an existing Sabha user (`LOGIN_AS`, an email); the API still takes roles and tenant
  from its own records, so no permission is bypassed.
- The password is stored only as a scrypt hash (standard library; `scripts/admin/hash_password.py`) and checked in
  constant time. A wrong username or password gets the same 401.
- Tokens are signed with a key made at start-up, so restarting the API signs everyone out. There is no lockout:
  it is not for deployed environments, where Auth0 (above) is the plan.

<a id="doc-docs-adr-0003-local-object-storage-md"></a>

## ADR 0003: RustFS for local object storage

*Source: [`docs/adr/0003-local-object-storage.md`](adr/0003-local-object-storage.md)*

- **Status:** Accepted
- **Date:** 2026-10-14
- **Plan task:** 1.1

### Context

`CLAUDE.md` and ADR 0001 chose MinIO as the S3-compatible store for local development; staging and production use
AWS S3 in `ap-south-1`. When P1.1 set up `infra/docker-compose.dev.yml`, MinIO images no longer existed:

- `docker manifest inspect` found no `minio/minio` or `minio/mc` tags on Docker Hub (the repository returns
  "object not found") and none on `quay.io/minio/*`.
- The last MinIO GitHub release was `RELEASE.2025-10-15T17-29-55Z`, a year before this decision.

Building an unmaintained server from source for every developer was not attractive, so we compared maintained,
Apache-2.0 alternatives against what Sabha needs from S3 (P2.1 and P2.2 uploads, P1.3 lifecycle tags).

### What we tested

A probe script ran the same operations against each candidate:

| Check | RustFS 1.0.0 | SeaweedFS 4.48 |
| --- | --- | --- |
| Create the three buckets | pass | pass |
| Put, get, delete | pass | pass |
| Object tagging (`data-class=audio`) | pass | pass |
| Wrong secret rejected | pass | pass |
| Bucket CORS stored | pass | pass |
| Presigned multipart upload of two parts, tags kept, `ETag` exposed on PUT | pass | pass |
| CORS preflight allowed for the web origin | pass | pass |
| CORS preflight refused for another origin | pass | pass |
| Image size | 401 MB | 724 MB |
| Idle memory | about 160 MB | about 182 MB |

LocalStack's repository is archived; Garage is AGPL-3.0 and needs more configuration.

### Decision

Use **RustFS** (`rustfs/rustfs:1.0.0`) locally. It is built as a MinIO replacement, has the same access-key
model and a web console, and is the lighter of the two, which matters on developer machines with little RAM.
Buckets and CORS rules are created by `scripts/dev_storage.py`, which `make dev` runs (the MinIO `mc` image is
gone too).

### Consequences

- Nothing changes for staging and production: they use AWS S3, and the app refuses `S3_ENDPOINT_URL` there.
- Application code only uses the S3 API through boto3, so switching to SeaweedFS later means changing the image
  and start-up command in `infra/docker-compose.dev.yml`, not code.
- RustFS 1.0 is young. If a behaviour differs from S3, the AWS behaviour wins; record the gap and test it
  against staging.

<a id="doc-docs-adr-0005-fairness-md"></a>

## ADR 0005: Fair GPU scheduling across tenants

*Source: [`docs/adr/0005-fairness.md`](adr/0005-fairness.md)*

- **Status:** Proposed
- **Date:** 2026-10-16
- **Plan task:** 7.2

### Context

All tenants share the GPU that runs diarization and speech recognition (queue `gpu.speech`, one task at a time per
GPU). Without control, one school uploading a term's worth of lessons would make every other school wait hours,
including for a five-minute front-desk call whose report someone needs today. The goal from the plan: short calls
finish within 5 minutes during a bulk upload from another tenant.

### Decision

1. **Schedule chunks, not recordings.** The GPU works on chunks of about 30 seconds of compact audio (P3.5). A
   three-hour lesson becomes hundreds of chunks that interleave with other work, so nothing waits behind a whole
   recording. This is the precondition for any fairness: with whole recordings as jobs, the worst-case wait is the
   longest recording in the queue.
2. **Two lanes.** Chunks of recordings shorter than 10 minutes go to a short lane, everything else to a normal lane.
   The short lane is served first, but after 3 consecutive short picks the normal lane gets one turn when it has
   work, so long lessons are never starved.
3. **Weighted deficit round robin across tenants within each lane.** Tenants with queued chunks take turns. On its
   turn a tenant's credit grows by `quantum x weight` (quantum 30 s; weight from the tenant's plan, default 1) and it
   sends chunks from the front of its queue while their cost fits. Each backlogged tenant therefore gets GPU time in
   proportion to its weight regardless of backlog size; a tenant that goes idle leaves the round and loses unused
   credit, so it cannot save up a burst. Chunks of one tenant stay in order.
4. **Admission control.** When the `gpu.speech` backlog is old, the upload API still accepts uploads and returns an
   estimated completion time: queued audio ahead plus the recording's own audio, divided by the GPU throughput
   measured from recent `stage_runs`. The throughput is always measured, never assumed.

The algorithm is `apps/workers/sabha_workers/fair_scheduler.py`; the gpu.speech dispatcher (P2.4) owns one
scheduler and feeds the GPU worker one chunk at a time.

### How the 5-minute target follows

For a short call arriving during another tenant's bulk upload, the wait before its first chunk is at most the chunk
in progress plus one normal-lane chunk; its chunks then run back to back, with one normal chunk after every 3. Its
completion time is therefore about `(its chunks x 4/3 + 2) x time per chunk`. Whether that is under 5 minutes depends
on the GPU's measured time per chunk, which the load test (plan task 7.5) measures on the staging L4. No speed is
assumed here. The simulation tests in `apps/workers/tests/test_fair_scheduler.py` check the ordering guarantees.

### Alternatives considered

- **Separate Celery queues per tenant:** many queues to manage, and fairness depends on worker polling order.
- **Plain priority by recording length:** starves long lessons under a steady stream of short calls.
- **Strict round robin by recording:** a long lesson still holds the GPU for its whole duration.

### Consequences

- The dispatcher must persist scheduler state (queues and credits) so a restart does not reorder or lose chunks;
  this belongs to the P2.4 worker design.
- Tenant weights become a plan setting. Changing them changes everyone's share, so changes are audited.
- Per-chunk dispatch adds a little overhead per chunk; the in-process batcher (P3.5) recovers GPU efficiency by
  batching chunks that are dispatched together.

<a id="doc-docs-adr-0006-asr-sarvam-md"></a>

## ADR 0006: Sarvam AI for speech recognition, with approximate word timing

*Source: [`docs/adr/0006-asr-sarvam.md`](adr/0006-asr-sarvam.md)*

- **Status:** Accepted
- **Date:** 2026-10-17
- **Plan task:** 3.1

### Context

The plan expected to port an ASR layer from an earlier "LIS" codebase. That codebase does not exist (ADR 0001
correction), so `packages/asr` builds its provider layer from scratch. The owner chose Sarvam AI's hosted
speech-to-text as the first provider: it targets Indian languages and Hindi-English switching, needs no GPU, and
Sarvam says it processes data in India (golden rule 12).

Sarvam's REST API (docs.sarvam.ai, read 2026-10-17) differs from what the pipeline assumed:

| The pipeline assumed | Sarvam's `POST /speech-to-text` |
| --- | --- |
| A start and end time per word | `timestamps` = parallel lists `words`, `start_time_seconds`, `end_time_seconds`, where each "word" is a phrase or sentence |
| A confidence per word | No confidence |
| Chunks of about 30 s | At most 30 s per request (the Batch API takes 2 h, also phrase-level, and is asynchronous) |

### Decision

1. **Sarvam's REST API, one request per chunk.** Chunks stay under 29.5 s. Model `saaras:v4` by default
   (`ASR_MODEL` overrides; `saaras:v3` gets `mode=transcribe`). `language_code=unknown` detects the language unless
   `ASR_LANGUAGE` sets one.
2. **Approximate word timing.** Each phrase is split on whitespace and its time is shared among its words in
   proportion to their length (`sabha_asr.provider.spread_words`). Transcripts record `word_timing: "approximate"`.
3. **Word confidence is optional.** `Word.confidence` and `avg_confidence` may be null. Words without confidence are
   never marked low-confidence, so the transcript view shows no "unclear" highlighting for Sarvam transcripts.
4. **One provider, explicit fallbacks only.** `ASR_PROVIDER` picks one; `ASR_FALLBACKS` (empty by default) lists
   others to try in order. Every fallback use is logged with the reason and recorded in the outcome
   (golden rule 7). The fake provider is refused in staging and production.
5. **Retries** follow Sarvam's error guide: 429 (except `insufficient_quota_error`), 500 and 503, timeouts and
   network errors are retryable; 400, 403, 413, 422 and out-of-credits are not. Retrying belongs to the stage.

### Consequences

- **Speaker attribution is phrase-accurate, not word-accurate.** Words are given to speakers by their times. A
  phrase in which the speaker changes is split approximately, which affects talk share, question counts and quote
  timestamps. We measure speaker-attribution error on the gold set (P4.3 roles eval) before trusting these numbers.
  If it is too high, the next step is a self-hosted forced aligner on the GPU worker for real word times.
- **Playback positions** for quotes are accurate to the phrase, not the word.
- **Before any real recording is sent:** confirm in writing Sarvam's data location, retention (zero-day retention
  is offered on request) and that inputs are not used for training. Their public pages and third-party summaries
  disagree on training terms. Until then, use only test audio.
- **Cost and speed** are unknown until measured: the transcriber records audio and compute milliseconds per batch
  (real-time factor), and stage runs keep them for cost reports. No figures are assumed here (golden rule 6).
- **Dependencies:** `httpx` in `sabha-asr` (sync HTTP for the Celery worker).
- Adding another provider (for example a self-hosted model chosen by a bake-off) is one adapter, one registry entry
  and the shared contract tests in `packages/asr/tests/test_provider.py`.
- **Sped-up audio (experimental, 2026-11-04).** `ASR_SPEEDUP=true` with `ASR_SPEEDUP_FACTOR` (above 1.0, at most
  1.5; default 1.25) speeds each chunk up with ffmpeg `atempo` (pitch kept) before it is sent. Sarvam bills by
  audio length, so 1.25 sends 48 s per minute of speech. Returned times are multiplied back by the factor, so
  transcripts stay on the normal timeline; `asr@v1.json` and the stage run record `speed`. It is off by default.
  Accuracy may drop, above all on fast Hindi-English speech. Before turning it on, transcribe the gold set twice
  (off and on) and compare both with `eval/wer.py`; keep it only if WER and CER, overall and on the Hinglish
  mixes, do not get worse. No accuracy or saving figures are assumed here (golden rule 6).

<a id="doc-docs-adr-0007-review-outcomes-md"></a>

## ADR 0007: How a recording leaves "Needs review"

*Source: [`docs/adr/0007-review-outcomes.md`](adr/0007-review-outcomes.md)*

- **Status:** Accepted
- **Date:** 2026-10-23
- **Plan task:** 6.7 (the needs-review half; disputes follow)

### Context

The pipeline stops a recording at NEEDS_REVIEW when it should not guess: the speakers' roles are unclear, no speech
or no words were found, too few scores could be checked against the transcript, the summary failed, or the
conversation type is uncertain. Until now nothing left NEEDS_REVIEW (`sabha_core/state.py`), so such a recording
stayed stuck and nobody could act on it in the app. Real classroom audio will hit "unclear roles" regularly (two
adults, a quiet teacher, group work).

### Decision

Decided by the product owner on 2026-10-23.

1. **Unclear roles: a reviewer says who the staff member is, and Sabha carries on.** The reviewer sees each speaker
   with their talk time, Sabha's best guess and a few sample lines with playback, and picks the teacher (or
   receptionist). That speaker gets the rubric's staff role and every other speaker the other role. The roles are
   stored on the recording (`confirmed_roles`) and it moves NEEDS_REVIEW -> TRANSCRIBING. The transcribe stage
   runs again: the speech recognition is reused from its checkpoints (no second provider call or charge), the
   transcript is rebuilt with the confirmed roles (method "reviewer"), and the recording goes on to analysis.
2. **Every other reason: explained, and the reviewer may only close it.** "Close: not usable" needs a note and moves
   NEEDS_REVIEW -> FAILED with reason `closed_by_reviewer`. Re-running analysis is not offered yet (each attempt
   costs an LLM call; it can be added as its own outcome later).
3. **Who decides.** Reviewers and managers for their units, owners and admins for everyone. Staff never resolve a
   review, not even of their own recording.
4. **Both outcomes are review transitions.** They are allowed only with `review=True` in the state machine (like
   re-analysis's `reanalysis=True`), so no other code path can move a recording out of NEEDS_REVIEW by accident.
   Each is one transaction with its outbox event and an `audit_log` entry (`recording.review`, with the decision,
   the roles or the note).

### Consequences

- `GET /v1/reviews`, `GET /v1/recordings/{id}/speakers` and `POST /v1/recordings/{id}/review` (in the permission
  matrix); the web app's Reviews page.
- Golden rule 5 still holds: a guess is never analysed. Analysis only runs on roles a person confirmed.
- Students' words appear in the speaker samples, as they already do in the transcript a manager can read. Students
  are still never scored or profiled (golden rule 10).
- Confirmed roles that no longer fit the transcript (a speaker missing, not exactly one staff member) send the
  recording back to review instead of being guessed around.

<a id="doc-docs-adr-0008-meetings-md"></a>

## ADR 0008: Meetings are analysed as a whole

*Source: [`docs/adr/0008-meetings.md`](adr/0008-meetings.md)*

- **Status:** Accepted
- **Date:** 2026-10-26
- **Plan task:** product owner's re-plan of 2026-10-24 (sales, meetings and company reception before infrastructure)

### Context

Every other conversation type analyses one staff member (teacher, receptionist, sales rep); the rest of the
speakers are context. A team meeting, such as a founder's weekly meeting, has no such person, and scoring
individual participants against each other would turn Sabha into a tool for ranking colleagues.

### Decision

Decided by the product owner on 2026-10-24.

1. **The meeting is scored, never a person.** The rubric (`rubrics/meeting.company.v0.1.yaml`) has one role,
   `participant`. The transcript step gives every voice that role (method `all_participants`), so there is nothing
   to guess and nothing to review. The prompts say the meeting is judged as a whole and never score, rank, praise or
   criticise an individual. The meeting's analysis and scores have no `person_id`, so they appear in nobody's
   trend; the recording keeps its organiser (who uploaded it) only for who may see it.
2. **Meeting notes come with the report** (`sabha_analytics.meetings`): decisions, action items (what, who as named
   in the meeting, the voice that took it when clear, and the date as said) and open questions. Every item rests on a
   quote verified like rubric evidence; unverified items are left out and counted.
3. **Voices, not people.** For meetings only, the model sees each line's anonymous voice label (S0, S1, ...) so it
   can say who took an action. Participation is measured in code as aggregates (`voice_count`, `top_voice_share`,
   `quiet_voice_count`); these metrics are never computed for lessons or calls, where counting voices would drift
   towards analysing students or callers (golden rule 10).
4. **Naming voices is display only.** Anyone who may see a meeting may name its voices (`PUT
   /v1/recordings/{id}/voices`, audited). Names are stored on the recording, shown in the transcript and the notes,
   and never sent to a model.

### Consequences

- Meetings are switched on for the company profile with the draft rubric; the demo company has them.
- Golden rule 10 is unchanged for lessons: voice labels and voice metrics stay out of every non-meeting analysis.
- Restart workers before the API when deploying (Recording gains `voice_names`; docs/runbook.md).

<a id="doc-docs-adr-0009-transcript-upload-md"></a>

## ADR 0009: Meeting transcripts can be uploaded instead of audio

*Source: [`docs/adr/0009-transcript-upload.md`](adr/0009-transcript-upload.md)*

- **Status:** Accepted
- **Date:** 2026-11-02
- **Plan task:** product owner's request of 2026-11-02 (sales calls held on Google Meet)

### Context

Many conversations, sales demos especially, now happen on Google Meet, which writes its own transcript. When that
transcript exists, cleaning the audio, separating the speakers and speech-to-text are slow and paid work that the
meeting tool has already done, and its speaker names are more reliable than voice clustering. The audio is often
not kept at all. Users asked to upload the transcript when there is one, and the audio when there is not.

A Meet transcript (.txt) has `Name: text` lines and a time marker about once a minute, not one per line. Some
exports label speakers "Speaker 1", "Speaker 2" instead of names.

### Decision

Decided by the product owner on 2026-11-02.

1. **One upload, two kinds of file.** The upload page and `POST /v1/recordings` take a `.txt` (text/plain, at most
   5 MB) next to the audio formats. The recording gets `source: "transcript"` (otherwise `"audio"`). Everything
   else is unchanged: the same direct-to-storage upload (the API never reads the file), the same consent rule
   (golden rule 9), the same rubrics, review and results.
2. **One guarded shortcut in the state machine.** An imported transcript goes `UPLOADED -> TRANSCRIBING`, allowed
   only with `imported=True` *and* only when the stored recording's `source` is `"transcript"`, checked in the same
   conditional update. An audio recording can never skip its stages. Retries, review (`NEEDS_REVIEW ->
   TRANSCRIBING`) and re-analysis work as before.
3. **The transcribe stage reads the file** (`sabha_workers.stages.imported`, reader in `sabha_asr.imported`), then
   hands words and turns to the same roles and transcript step as speech recognition. Finding the sales rep (or
   receptionist, or teacher) uses the existing heuristics, the LLM tie-breaker and a reviewer, so "Speaker 1/2"
   files need nothing extra.
4. **Times are estimates, and say so.** Lines between two markers share that stretch in proportion to their length;
   the transcript is stored with `word_timing: "approximate"` and the results page says times are approximate, to
   about a minute. The text is exactly the file's, so quotes are verified against it as for audio (golden rule 5).
   A file with no time markers is refused (`no_timestamps`): every judgement must cite a time.
5. **No invented numbers.** A transcript says nothing about silence, so the silence metrics are left out for it
   rather than shown as zero. Talk share and monologue length come from the estimated times.
6. **Names stay out of models.** Speakers become S1, S2, ...; the names in the file are kept on the recording as
   `voice_names` for display only. A name spoken aloud in the conversation stays in the text, as with audio.
7. **Meeting time.** When the uploader gives no time, the start time in Meet's file name ("2026_11_02 11_18 IST")
   is stored as `recorded_at`.

### Consequences

- No speech provider is called and nothing is billed for speech on these recordings.
- There is no audio to play; evidence links jump to the transcript line instead.
- Only Google Meet's .txt layout is read so far. Word (.docx) exports and other tools (Zoom and Teams .vtt) can be
  added as further readers in `sabha_asr.imported` without changing the pipeline.

<a id="doc-docs-adr-0010-no-github-actions-md"></a>

## ADR 0010: No GitHub Actions

*Source: [`docs/adr/0010-no-github-actions.md`](adr/0010-no-github-actions.md)*

- **Status:** Accepted
- **Date:** 2026-11-02
- **Supersedes:** the CI part of plan task P1.2 and the "GitHub Actions" row of ADR 0001

### Context

`.github/workflows/ci.yml` ran lint, tests and security audits on every pull request and push to `main`. The product
owner wants a plain repository on GitHub: pushes only, nothing in the Actions tab.

### Decision

Decided by the product owner on 2026-11-02. The workflow file is deleted and no other workflow is added. Before
pushing, developers run `make lint` and `make test` locally; pre-commit still runs detect-secrets on every commit.

### Consequences

- Nothing checks a push automatically. A broken test or lint error reaches `main` unless someone ran the checks.
- `pip-audit`, `pnpm audit` and gitleaks no longer run on their own; run them by hand when dependencies change.
- Image publishing to `ghcr.io` and the planned eval gate (P4.7) need another home if they are wanted later.

<a id="doc-docs-adr-0011-evidence-based-speaker-roles-md"></a>

## ADR 0011: Evidence-based speaker roles for support calls

*Source: [`docs/adr/0011-evidence-based-speaker-roles.md`](adr/0011-evidence-based-speaker-roles.md)*

- **Status:** Accepted
- **Date:** 2026-11-04
- **Amends:** the role rules of plan task P3.6 (`sabha_asr.roles`) for conversation types with an evidence profile

### Context

Support calls swapped agent and customer. On one call nobody said the company's name, so the greeting rule had no
evidence, and the AI tie-breaker read a garbled opening and named the customer as the agent with 89% confidence,
which Sabha accepted (its bar was 70%). On a support call, the agent is not the one who speaks first or explains
the problem: a customer often calls, talks most and explains at length.

### Decision

Decided by the product owner on 2026-11-04. Support calls always have exactly one agent and one customer.

1. **Evidence profiles per conversation type** (`sabha_asr.role_evidence`), support first. A profile lists
   behaviours (cues) pointing to the staff member or to the other side, with weights. Support: greets and names
   the organisation (+4, opening only), introduces as support (+3), asks for the AnyDesk ID (+3), guides software
   steps (+3), explains a module (+3), asks which school (+2) and more for the agent; introduces as a school
   representative (+3), describes a problem (+3), reads out the AnyDesk ID (+3) or a long number (+2), asks how to
   (+2) and more for the customer. Speaking first is +0.5. The weights are starting values, not measurements.
2. **Whole conversation.** A cue counts at most once per speaker; greetings count only in the first 30 s, the rest
   over the whole call. The first two minutes are weighed on their own too, and must not point to the other speaker.
3. **Both hypotheses.** "A is the agent" collects A's agent cues and B's customer cues, and the reverse. Confidence
   is 0.5 + 0.5 x margin x strength. Strong (>= 0.9) or corroborated (>= 0.75 with two different cues) evidence
   decides. Conflicting evidence (both sides strong, or the first minutes disagreeing) goes straight to a reviewer.
   Anything else goes to the AI.
4. **The AI as a tie-breaker only.** It is told what support calls look like and who the agent works for, reads the
   first five minutes, and must return quotes for both sides, each with its speaker. Quotes not found in what that
   speaker said are dropped; without one on each side, or if it asks for review, its answer is not used. On support
   calls it must be at least 90% sure and must not contradict the evidence's lean (confidence >= 0.6).
5. **Reviewer corrections are kept for measurement.** The automatic decision is saved in `roles_auto@v1.json` and
   the evidence in `role_evidence@v1.json`, never overwritten by a reviewer's confirmation;
   `eval/role_corrections.py` lists every correction against them.

Other types keep their rules until they get a profile.

### Consequences

- More support calls go to review at first: when the evidence is thin or contradictory, a person decides instead
  of the AI guessing. The review screen already asks "which speaker is the agent?".
- Cue phrases are Hindi and English as Sarvam writes them. Calls in other languages find few cues and go to the AI
  or a reviewer until the profile has phrases for them.
- The weights and thresholds must be calibrated on reviewer corrections and the gold set (`eval/roles.py`) before
  they are trusted; no accuracy is claimed here.

<a id="doc-docs-adr-0012-more-asr-providers-md"></a>

## ADR 0012: More speech-to-text providers, and comparing them on our own calls

*Source: [`docs/adr/0012-more-asr-providers.md`](adr/0012-more-asr-providers.md)*

- **Status:** Accepted
- **Date:** 2026-11-13

### Context

Sarvam (ADR 0006) is the only speech-to-text provider, at ₹0.49 per audio minute. The owner finds it costly and
wants to try cheaper models on the same calls and see the difference before switching. The owner chose: OpenAI,
Qwen (Alibaba Cloud), Amazon Transcribe and a self-hosted Whisper.

**Data residency.** Golden rule 12 keeps data in India. On 2026-11-13 the owner decided that, for these calls,
providers outside India are acceptable ("models all over the world would work"). This ADR records that decision.
OpenAI and Qwen's international endpoint (Singapore) process audio outside India. Amazon Transcribe in ap-south-1
(Mumbai) and the self-hosted Whisper keep it in India.

Prices, from each provider's own published figures (checked 2026-11-13, kept in `sabha_asr.pricing` with sources):

| Model | Published price | Word times |
| --- | --- | --- |
| `sarvam/saaras:v4` | ₹0.49 / min | phrases only |
| `openai/gpt-transcribe` | $0.0045 / min | none (text only) |
| `openai/gpt-4o-mini-transcribe` | $0.003 / min (deprecated, shut down 2027-02-26) | none |
| `qwen/qwen3-asr-flash` | $0.000035 / s ($0.0021 / min), international | none |
| `aws/transcribe@ap-south-1` | $0.0001 / s ($0.006 / min), Mumbai | per word |
| `whisper/*` (self-hosted) | no per-minute price; the machine it runs on | per word |

### Decision

1. **Four new providers behind the existing interface** (`packages/asr/sabha_asr/providers/`): `openai`, `qwen`,
   `aws`, `whisper`. Each returns the same `ChunkResult`s, so nothing after the transcribe stage changes. Providers
   without word times spread each chunk's text across it (word_timing "approximate"), as Sarvam's phrases are.
2. **Switching is configuration**: `ASR_PROVIDER` and `ASR_MODEL`, then a restart of the speech worker. Fallbacks stay
   explicit (`ASR_FALLBACKS`, golden rule 7).
3. **Prices keep their currency.** A dollar price becomes rupees only with the configured `USD_INR_RATE`; without it
   the rupee cost is None. AWS is priced for Mumbai only; another region costs None until its price is checked.
4. **A comparison tool, `eval/asr_compare.py`**, sends the same chunks of existing calls to each chosen model, reuses
   Sarvam's saved answers (no second payment), and writes a local HTML report: transcripts side by side, cost, speed,
   and how much each differs from Sarvam. Without human-checked transcripts (the gold set is empty) the difference is
   **not accuracy**: it says where the models disagree, and a person listens to decide who is right. Word error rate
   against a gold transcript is reported only by `eval/wer.py` (golden rule 6).
5. **Owners and admins may choose the model per upload** (added 2026-11-13 at the owner's request). The upload page
   lists the models in `sabha_asr.registry.CHOICES` with their price per audio hour (`GET /v1/speech-models`); ones
   whose key is missing are shown but cannot be chosen. The recording keeps the choice (`asr_choice`, audited on
   create), its cost estimate uses that model's price, and the speech worker builds that model for it. Other roles
   cannot choose (403); without a choice the configured model is used.
6. **Self-hosted Whisper is an optional install** (`uv sync --extra whisper`, faster-whisper). It is not part of the
   API or CPU worker images.

7. **Only English, Hindi and Hinglish in transcripts** (owner, 2026-11-13). Left to detect the language itself,
   OpenAI's models wrote parts of a Hindi call in Urdu and Bengali script. So:
   - With ASR_LANGUAGE "unknown", gpt-transcribe is told to expect Hindi and English (`languages` hi, en) and the
     older OpenAI models are told Hindi.
   - No sample `prompt` is sent. As a test, a Hinglish sample prompt was tried on one support call;
     gpt-4o-mini-transcribe copied it into 12 of 44 pieces, which would put words nobody said in the transcript.
   - The transcribe stage asks again, in Hindi, any chunk written in a script other than Latin and Devanagari, for
     every provider. A chunk still in another script is kept and counted (`still_other_script`), never dropped.
   - On that call: gpt-transcribe gave 0 of 44 pieces in another script. gpt-4o-mini-transcribe gave 18 of 44 in
     Urdu or Telugu script even with `language` hi, so it is no longer offered on the upload page.

### Consequences

- Providers without word times give coarser speaker attribution inside a chunk (as with Sarvam). Amazon Transcribe and
  Whisper give word times.
- Whisper picks one language per chunk; Hindi-English switching is written in the script it chose. Qwen takes one
  language hint or detects it. Sarvam and Amazon Transcribe (with language identification) handle switching inside a
  chunk.
- The comparison report holds call transcripts, so it stays on this machine (`eval/reports/`, not committed) and is
  not published.
- Golden rule 12 in CLAUDE.md still says "data stays in India"; this ADR is the owner's recorded exception for speech
  recognition.

### Addendum 2026-11-16: Groq

The owner added Groq (Whisper Large v3 and Whisper Large v3 Turbo, hosted by Groq in the US) under the same
residency exception. Groq serves OpenAI's transcription API, so `providers/groq.py` is the OpenAI provider with
Groq's address and models; both models return word times. Groq's published prices (0.111 and 0.04 USD per audio
hour, minimum 10 s billed per request) are in `sabha_asr/pricing.py`. Its per-minute limits are low on the free
plan, so Groq waits out a rate limit longer (8 retries) than OpenAI does.

### Addendum 2026-11-16: Deepgram and Gemini, for Hindi-English code-mix

The owner wants Hindi written in Devanagari and English words in Latin letters, at about Whisper's price. Whisper
cannot do this safely: without a language it translated Hindi into English and wrote Urdu; with a mixed sample prompt
it copied the sample into near-silent pieces. Added under the same residency exception:

- `deepgram` (Nova-3, `language=multi` with hi/en hints): code-mix with word times; 0.0052 USD per minute.
- `gemini` (`gemini-3.8-flash`, `gemini-3.5-flash-lite`): a general model told to transcribe verbatim, never
  translate, and write each word in its own script. No word times. An answer with more than 6 words per second of
  audio is asked again once, then fails the chunk, so invented text never reaches a transcript (golden rule 5).
  Priced on audio input only (25 tokens per second); output tokens cost extra and are not counted.

Which one to use is decided on accuracy against hand-corrected transcripts (eval/wer.py), not on the difference from
Sarvam.

### Addendum 2026-11-19: the upload list, and what Gemini costs per hour

Gemini bills by tokens: audio in, plus the written answer and any "thinking", both billed as output. Since
2026-11-18 every Gemini answer's token counts are stored and priced (`TokenUsage`, `TOKEN_PRICES` in
`sabha_asr/pricing.py`), and Gemini answering with a different model than asked fails the chunk instead of being
used quietly (golden rule 7).

Measured on NiaLabs calls, at the published prices:

| Model | Thinking | Cost per audio hour | Measured on |
| --- | --- | --- | --- |
| Gemini 3.8 Flash | Google's default | about ₹148 (thinking was 88% of it) | 2026-11-18 |
| Gemini 3.8 Flash | low (no thinking tokens used) | about ₹13.3 | 174 s of the Roshan call, 2026-11-19 |
| Gemini 3.1 Flash-Lite | minimal | about ₹11.0 | 2026-11-18 |

The upload page's price list counts audio input only for Gemini, so it shows less than these figures.

The upload list (owner):

- **Gemini 3.8 Flash** is back on the list on 2026-11-19, asked to think "low".
- **Gemini 3.1 Flash-Lite** is Gemini's default model (2026-11-18). Google retires it on 2027-05-07.
- **Gemini 2.5 Flash and 2.5 Flash-Lite** are not offered: Google refuses both to our account (HTTP 404, "no longer
  available to new users", 2026-11-18).
- **Qwen3 ASR Flash and Amazon Transcribe** are off the list on 2026-11-19. Their adapters stay for
  `eval/asr_compare.py`.

<a id="doc-docs-adr-0013-said-well-and-badly-md"></a>

## ADR 0013: What the agent said well and badly, checked against product information

*Source: [`docs/adr/0013-said-well-and-badly.md`](adr/0013-said-well-and-badly.md)*

- **Status:** Accepted
- **Date:** 2026-11-13

### Context

Sales and support managers said the report does not show what the agent said right and wrong. Two reasons:

- The went-well, needs-work and next-time lists are private coaching. Managers see only each rubric point's score,
  a short reason and quotes, and the quotes are not marked good or bad.
- Approved product information (`product_info`) was used only for the sales next-time coaching tips. A wrong price
  or policy never affected a score, and support used it not at all.

The owner decided on 2026-11-13:

1. A per-call list of plus points and drawbacks is the call's evaluation, so managers see it as well as the agent.
   Next-time coaching stays private.
2. A product statement that contradicts the approved information lowers the relevant scores.

### Decision

1. **A new step, `sabha_analytics.moments`**, runs for sales and support calls whether or not the scores verified.
   It lists up to 10 moments, each with:
   - `kind`: plus or drawback;
   - `text`: at most 30 words, in English, naming the agent by role, never by gender or name;
   - `evidence`: a verified quote (golden rule 5);
   - `fact`: for product statements, `matches` or `contradicts` with the approved entry's id, or `not_covered`.

   An id that was not given, or a verdict that does not fit its id, is refused and re-asked once. So a moment can
   never claim a check against unapproved information, and a statement the information does not cover is never
   called wrong. Moments whose quote is not found are left out and counted.
2. **Scoring sees the approved information for sales and support.** The scoring context (`scoring.context` v2) gets
   an "Approved product information" section with one rule: a contradicted fact lowers the product, value, price
   or troubleshooting dimensions, and the rationale says what the entry says. Other types get no section, so their
   prompt is unchanged.
3. **The API returns `moments` to everyone who may see the report** (not in `PRIVATE_COACHING`), with each entry's
   title and text attached.
4. **The report page** shows a one-line count at the top ("3 plus points, 5 drawbacks (3 wrong product facts)") that
   opens a "What <name> said" panel: plus points and drawbacks side by side, each with its time, quote and the entry
   it matched or contradicted.
5. **Up to 80 active product information entries** (was 40). All of them go into the scoring, moments and coaching
   prompts, about 45 × 800 characters today.

### Consequences

- One more LLM call per sales or support analysis, and a longer scoring prompt when entries exist. Prompt caching
  covers the repeated prefix.
- How often the model's fact verdicts are right is not yet measured. There is no human-annotated set for it
  (golden rule 6). The verdicts cite the entry, so a manager can check one with a click.
- Reports made before this decision have no `moments`. Re-analysis adds them.

<a id="doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md"></a>

## ADR 0014: Number of speakers and the Gemini speaker check, chosen at upload

*Source: [`docs/adr/0014-speaker-count-and-gemini-speaker-check.md`](adr/0014-speaker-count-and-gemini-speaker-check.md)*

- **Status:** Accepted
- **Date:** 2026-11-18 (model updated 2026-11-19)

### Context

On the Roshan sales call (NiaLabs demo, 2026-11-18) the opening, 0:06 to 0:33, was given to one speaker although
the customer and the sales rep take turns of a second or two. pyannote separates voices by sound alone; on a mono
phone line with two similar voices it merged them, and Deepgram's own speaker labels did the same. Running pyannote
on the full original audio instead of the speech-only audio did not help.

Gemini, given the audio and the transcript lines, also follows the conversation (a question and its answer are
said by different people) and got the opening right.

The owner decided on 2026-11-18:

1. Whoever uploads may say how many people speak in the recording.
2. Whoever uploads may ask for a Gemini check of who said each line, on top of pyannote.

### Decision

**Number of speakers** (`Recording.speaker_count`, 2 to 10, or automatic). The diarizer is asked for exactly that
many. Order: the uploader's number, then 3 for a support call a colleague helped on ([ADR 0015](#doc-docs-adr-0015-colleague-helped-calls-md)),
then the type's default (support calls: 2), otherwise pyannote decides. With 2 speakers, one is the staff member
and the other the customer.

**Speaker model** (`Recording.speaker_model`): `pyannote` (default) or `gemini` (pyannote plus the check).
The check, in `packages/asr/sabha_asr/speaker_check.py`, runs in the transcript step:

1. The words become lines: one speaker's words up to a sentence end or a change of speaker.
2. Gemini gets 3-minute windows of the **original** audio with the numbered lines heard in each. Line text is
   PII-masked first (golden rule 8). It answers with the numbers of the staff member's lines and the lines it
   cannot tell; the rest are the customer's.
3. A line of at least 3 words that Gemini gives to the other side moves there. Shorter lines ("ठीक", "ओके") and
   lines it cannot tell stay as pyannote had them. pyannote's turn times are kept; only whole lines move.

The result is stored as `speaker_check@v1.json` and on the transcript (`Transcript.speaker_check`: model, lines,
moved, unsure, cost). Its cost is added to the recording's speech-to-text cost.

**Model:** Gemini 3.8 Flash with thinking set to low (owner, 2026-11-19). On the Roshan call (12 minutes,
2026-11-18) it moved 39 to 40 of 264 lines over two runs, could not tell 1 to 6, got the opening right and cost ₹2.16 (about ₹10.8 per audio
hour). Gemini 3.1 Flash-Lite cost about ₹6.8 per hour but moved 25, could not tell 86 and left Roshan's own lines
with the customer. Gemini 2.5 Flash and 2.5 Flash-Lite are refused to our account (HTTP 404, "no longer available to
new users", 2026-11-18).

### Consequences

- If Gemini fails, the stage fails and is retried like speech-to-text. A transcript is never produced without a
  check that was asked for (golden rule 7).
- Audio goes to Google (outside India) under the speech-recognition residency exception of
  [ADR 0012](#doc-docs-adr-0012-more-asr-providers-md). Only send audio you have consent for.
- The 3-word minimum is a starting value, not measured. Whether the check improves speaker accuracy overall needs
  hand-labelled calls (`eval/roles.py`); one call is not a measurement.
- Gemini 3.8 Flash's input price doubles from 2027-01-01 (`sabha_asr/pricing.py`).

<a id="doc-docs-adr-0015-colleague-helped-calls-md"></a>

## ADR 0015: Support calls a colleague helped on stay the first agent's

*Source: [`docs/adr/0015-colleague-helped-calls.md`](adr/0015-colleague-helped-calls.md)*

- **Status:** Accepted
- **Date:** 2026-11-19 (replaces the per-agent design of 2026-11-18)

### Context

In company support, an agent who cannot solve a problem sometimes hands the phone to a more experienced colleague
sitting beside them. One recording then holds three voices: the customer, the agent and the colleague.

On 2026-11-18 this was first built as a transfer between two agents, each to be scored on their own part. On
2026-11-19 the owner corrected it: the colleague only helps on the agent's phone. The call is technically the first
agent's, so every number, score and piece of coaching goes to them. Per-agent scoring was dropped for good.

### Decision

1. **Upload.** For support audio the upload page asks "Did a colleague help on this call?"
   (`Recording.transferred`). Anyone who uploads may say yes, staff included. Uploaders other than staff may also
   name the colleague under "Who helped (optional)" (`Recording.transfer_person_id`). Staff cannot name anyone
   (403); the colleague must be in a unit the uploader may see.
2. **Diarisation.** Exactly 3 speakers are asked for ([ADR 0014](#doc-docs-adr-0014-speaker-count-and-gemini-speaker-check-md)).
   On call 4 of the NiaLabs demo, 2 speakers merged the two agent voices; 3 separated them.
3. **Roles.** `sabha_asr/transfer.py` finds the customer and the two agent voices: the customer is heard
   throughout, while the agents split the call around a handover point. A voice needs 90% of its speech on one
   side of the handover to count as an agent. The rubric's evidence-based roles ([ADR 0011](#doc-docs-adr-0011-evidence-based-speaker-roles-md))
   can only block the result, when they say an "agent" voice sounds like the customer. Unclear results go to
   review, as before.
4. **Scoring.** Both agent voices get the staff role. Metrics are per role, so talk share, questions and pace
   count the two agents together, and the whole call is scored as the first agent's. `transfer@v1.json` and
   `Transcript.agents` keep which voice is which person (the colleague's only when named) and `handover_ms`.

### Consequences

- The report and the people pages show the call under the first agent only. The colleague gets no score from it.
- A colleague who talks a lot raises the agent side's talk share. That is accepted: the call is judged as the
  team's handling of the customer, credited to the agent who owns it.
- Support only. Sales calls, meetings and school recordings are unchanged.

<a id="doc-docs-adr-0016-no-automated-tests-md"></a>

## ADR 0016: Automated tests removed

*Source: [`docs/adr/0016-no-automated-tests.md`](adr/0016-no-automated-tests.md)*

- **Status:** Accepted
- **Date:** 2026-11-19

### Context

The repo had about 190 test files: pytest suites in every package and app (integration tests ran MongoDB, Redis
and S3 in Docker through testcontainers), cross-package security tests (tenant isolation, raw collection access,
the permission matrix for every route), web unit tests (Vitest) and Playwright browser tests. With no CI
([ADR 0010](#doc-docs-adr-0010-no-github-actions-md)) they ran only by hand.

On 2026-11-19 the owner decided to delete all test files, after being told this goes against the rule in
`CLAUDE.md` that every change carries tests.

### Decision

- All test files are deleted, with `conftest.py`, the Playwright config and the browser tests, and the developer
  demo pages under `apps/web/src/dev/`.
- `make test`, `make test-py`, `make test-web`, `make test-fast` and `make e2e` are gone, as are the pytest settings
  in `pyproject.toml` and the web test settings.
- The permission matrix stays, as a record of who may call which route: `docs/security/permissions.yaml`. Nothing
  enforces it any more; a new route needs its row added by hand.
- `make lint` (ruff, mypy, eslint, prettier, tsc) is the one automated check left.

### Consequences

- Nothing checks tenant isolation, grounding, idempotency, the state machine or permissions automatically. A
  change to any of them must be checked by hand in the running app.
- The test tools (pytest, testcontainers, Vitest, Playwright, jsdom) are still dev dependencies; removing them
  changes the lock files and is a separate step.
- All deleted tests are in git history (before commit `ad2408d`) and can be restored with `git checkout`.

<a id="part-6"></a>

# Part 6. Reference

<a id="doc-docs-llm-providers-md"></a>

## LLM providers

*Source: [`docs/llm-providers.md`](llm-providers.md)*

Plan task 0.6. A comparison sheet to fill in from each provider's own documents and written answers. Every value
starts as **TBD** and is replaced only with something a provider has published or written to us, with the source
link and the date checked. Nothing here comes from memory (golden rules 6 and 12).

### Decision so far

- **2026-10-24:** OpenAI **shut down `o3-mini` on 2026-10-23** (deprecations page, checked 2026-10-24: replacement
  suggested `gpt-5.6-sol`); our calls failed with HTTP 404 "model has been deprecated". The product owner chose
  **`gpt-6-luna`** for both tiers (scoring and synthesis, and the role tie-breaker), the lowest-priced current model.
  Rejected as stop-gaps: `gpt-5` and `gpt-5-mini`, which OpenAI shuts down on 2026-12-11, inside the pilot.
  Whether luna judges as well as a larger model is not yet measured: the bake-off (P5.3) compares models on
  human-rated recordings, and no quality figure is claimed until then (golden rule 6).
- **2026-10-16:** the product owner chose **OpenAI** with the model **`o3-mini`** for scoring and synthesis.
  To confirm from OpenAI's documentation and our API dashboard, not from memory:
  - that `o3-mini` is available to our API project and not scheduled for retirement;
  - which reasoning-effort setting to use (the bake-off can compare them);
  - whether it accepts a `temperature` parameter. The plan (P5.6) assumes temperature 0 for repeatable scores; if
    a reasoning model does not take one, the bake-off (P5.3) must measure score stability across repeated runs
    instead of assuming it.
- ChatGPT is the consumer app. Sabha calls the **OpenAI API** with the key of a dedicated Sabha project, under the
  API's terms, not a ChatGPT account.
- **Not yet approved for real school data.** Golden rule 12 keeps data in India. Before any real transcript is
  sent, the residency and retention answers below must be in writing and the lawyer must answer
  `docs/legal/drafts/questions-for-lawyer.md`, group E (cross-border AI processing). Only then does an
  `OPENAI_API_KEY` go into the staging or production configuration. This is a process rule: the code does not
  enforce it (decided 2026-10-16), so whoever configures a deployment checks it.
- Text sent is always redacted first (phones, Aadhaar-like and PAN-like numbers, emails, listed student names;
  `packages/llm/sabha_llm/redact.py`). That reduces what leaves, but it is not a residency answer.

### Comparison

One row per provider. The bake-off (plan task 5.3) compares up to three; rows 2 and 3 stay empty if OpenAI is the
only candidate.

| Field | OpenAI | Candidate 2 | Candidate 3 |
| --- | --- | --- | --- |
| Models we would use: mid tier (scoring, synthesis) | `gpt-6-luna` (chosen 2026-10-24). Model page, 2026-10-24: no deprecation or shutdown date listed; Responses API; structured outputs supported. Was `o3-mini` (chosen 2026-10-16, shut down 2026-10-23) | TBD | TBD |
| Models we would use: small tier (role tie-breaker) | `gpt-6-luna` (chosen 2026-10-24) | TBD | TBD |
| Reasoning effort / temperature support | `gpt-6-luna`: reasoning effort none, low, medium (default), high, xhigh, max (model page, 2026-10-24); temperature not stated, so not sent | TBD | TBD |
| India region available (yes / no / how) | TBD | TBD | TBD |
| Data retention policy (API inputs and outputs) | TBD | TBD | TBD |
| Training on our data (default, and how to opt out) | TBD | TBD | TBD |
| DPA available (and covers DPDP Act, 2023?) | TBD | TBD | TBD |
| Structured output / JSON schema support | Supported (model page, 2026-10-19) | TBD | TBD |
| Prompt caching (how, minimum prefix, price) | `gpt-6-luna`: cached input $0.01, cache writes $0.125 per million tokens (model page, 2026-10-24). Automatic; usage reports `cached_tokens` and `cache_write_tokens`, both part of `input_tokens` (seen in our own calls, 2026-10-26) | TBD | TBD |
| Batch API and discount | TBD | TBD | TBD |
| Rate limits for our tier | TBD | TBD | TBD |
| Price per million input tokens | $0.10 (`gpt-6-luna`, model page, 2026-10-24); was $1.10 (`o3-mini`, 2026-10-19) | TBD | TBD |
| Price per million output tokens | $0.50 (`gpt-6-luna`, model page, 2026-10-24); was $4.40 (`o3-mini`, 2026-10-19) | TBD | TBD |
| Source link(s) | https://developers.openai.com/api/docs/models/gpt-6-luna, https://developers.openai.com/api/docs/deprecations (o3-mini: https://developers.openai.com/api/docs/models/o3-mini) | TBD | TBD |
| Date checked | 2026-10-24 (o3-mini: 2026-10-19) | TBD | TBD |

Prices go into the gateway's price table (plan task 5.1) only from this sheet, with the date; cost figures are
never estimated.

### Decision rule

In this order:

1. **Data residency.** A provider that cannot keep processing and storage in India, or whose cross-border
   processing the lawyer has not approved for redacted transcripts, is out, however good it is.
2. **Agreement with human raters** in the bake-off (plan task 5.3): JSON validity, grounding pass rate (quotes
   found in the transcript), stability across repeated runs, and agreement with the calibration raters.
3. **Cost**, from the prices in this sheet and the measured tokens per recording.

The choice is recorded in `docs/adr/0004-llm-choice.md` with the bake-off report.

### Email to send each provider

> **Subject:** Data residency, retention and DPA terms for API use (education product, India)
>
> Hello,
>
> We are building Sabha, a product that gives teachers and school staff in India feedback on recorded lessons
> and front-desk calls. We plan to use your API to score transcripts against a teaching rubric. Personal data
> (phone numbers, ID numbers, emails and students' names) is removed before any text is sent, but the text is
> still classroom speech from schools in India, so we need the following in writing before we use the API with
> real data:
>
> 1. **Data residency.** Can API requests be processed and any data stored only in India? If so, how is this
>    set up (region, endpoint, project or account setting) and for which models? If not, in which countries
>    are requests processed and stored?
> 2. **Retention.** How long are API inputs, outputs and logs kept, including for abuse monitoring? Is zero or
>    reduced retention available, and how is it enabled?
> 3. **Training.** Are API inputs or outputs used to train or improve models, by default or ever? How is this
>    confirmed for our account?
> 4. **Data processing agreement.** Do you offer a DPA, and does it address India's Digital Personal Data
>    Protection Act, 2023? Please send the current version.
> 5. **Sub-processors.** Which sub-processors may handle our data, and where are they located?
> 6. **Models and features.** For o3-mini, please confirm whether it is available to our project and for how long,
>    whether it accepts a temperature setting, and structured output with a JSON schema, prompt
>    caching, batch processing and the rate limits for our expected tier.
> 7. **Pricing.** Current input, output, cached-input and batch prices per million tokens for o3-mini.
>
> Links to the current published documents are fine where they answer a question. Thank you.
>
> [Name], [Role], Schoollog / Sabha
> [Email], [Phone]

<a id="doc-docs-webhooks-md"></a>

## Sabha webhooks

*Source: [`docs/webhooks.md`](webhooks.md)*

For developers who receive Sabha events in their own systems. A school or company configures an HTTPS endpoint and
receives a `POST` when a recording finishes.

### Events

| Type | When | Body (JSON) |
| --- | --- | --- |
| `recording.completed` | A recording's report is ready | `{"type", "event_id", "tenant_id", "recording_id", "occurred_at"}` |

Bodies never contain scores, quotes or transcript text. Fetch those from the API with your own credentials.
`event_id` is unique per event; the same event may be delivered more than once, so ignore an `event_id` you have
already processed.

### Verifying the signature

Every request carries a header:

```
Sabha-Signature: t=1760000000,v1=5f2b...e9
```

- `t` is the time Sabha signed the request, in Unix seconds.
- `v1` is the hex HMAC-SHA256 of the string `"<t>." + <raw request body>`, keyed with your endpoint's signing secret.

To verify:

1. Read the **raw** body bytes before any JSON parsing (re-serialised JSON will not match).
2. Compute `HMAC-SHA256(secret, "<t>." + body)` and compare it with `v1` using a constant-time comparison.
3. Reject the request if `t` is more than 5 minutes from your clock, to stop replays.

```python
import hashlib, hmac, time


def verify(body: bytes, header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, signature = int(parts["t"]), parts["v1"]
    if abs(time.time() - t) > 300:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

Sabha's own implementation is `apps/workers/sabha_workers/notifications/webhooks.py`.

### Retries

Respond with any `2xx` status within 10 seconds to acknowledge. Otherwise Sabha retries with exponential backoff,
starting at 30 seconds and doubling up to 2 hours between attempts, for up to 24 hours; after that the delivery is
marked failed in the tenant's delivery log.

<a id="doc-docs-security-findings-md"></a>

## Security findings (plan task P7.6)

*Source: [`docs/security/findings.md`](security/findings.md)*

One row per finding, kept up to date: severity, status and the fix (commit) or the reason it is accepted. "Done
when" for P7.6 is that no high-severity finding is open. Checks that need staging (OWASP ZAP baseline scan, S3
bucket policies, IAM, trivy on published images) are listed under "Not run yet" until they have been run; no
result is recorded for a check that did not run.

The automated tests named in some rows below were removed on 2026-11-19
([ADR 0016](#doc-docs-adr-0016-no-automated-tests-md)); those checks now need doing by hand. Commits before `ad2408d` still
hold them.

### Findings

| # | Date | Check | Finding | Severity | Status | Fix or reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-19 | `pip-audit` (all Python dependencies from `uv.lock`) | No known vulnerabilities | none | closed | None needed |
| 2 | 2026-10-19 | `pnpm audit` (apps/web) | [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm): `braces` via `tailwindcss` -> `chokidar` | high | accepted | No patched version exists; build-time only, inputs are our own config. Recorded in `apps/web/README.md`; goes away with Tailwind 4 |
| 3 | 2026-10-19 | `pnpm audit` (apps/web) | [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf): `postcss-selector-parser` 6.1.4 via `tailwindcss` (CPU exhaustion on hostile selectors) | moderate | accepted | Fixed only in 7.1.6, which Tailwind 3 (`^6.1.2`) cannot use. Build-time only: it parses our own CSS, never user input, and never ships to browsers. Goes away with Tailwind 4 |
| 4 | 2026-10-17 | `/tenant-check` | Per-user rate-limit key without tenant | low | fixed | 30a907b (P1.6) |
| 5 | 2026-10-17 | `/tenant-check` | Duplicate-key error reveals that an id exists in another tenant | low | fixed | 30a907b (P1.6): rule that ids are server-generated, with a test in `tests/security`; request bodies refuse `id` (P1.5b, P2.1) |
| 6 | 2026-10-17 | `/tenant-check` | Email delivery keys without tenant | low | fixed | 17b60cf: `deliveries` unique per (tenant, key) (P2.7) |
| 7 | 2026-10-20 | `strace` on the VAD step (P3.3) | `onnxruntime` 1.30 (Linux) ships Microsoft telemetry that opened HTTPS connections to Microsoft addresses (`mobile.events.data.microsoft.com`); `disable_telemetry_events()` did not stop it. A service outside India nobody approved (golden rule 12). No audio is involved, but usage data would leave | medium | fixed | P3.3: `ORT_DISABLE_TELEMETRY=1` is set by `sabha_workers/stages/vad.py` before onnxruntime is imported, and in the CPU worker image; strace then shows no connections. P3.4: pyannote also imports onnxruntime (speaker embeddings) and strace caught the same connections from diarization, so `sabha_asr/diarization.py` sets the variable too. A test fails if any module that imports onnxruntime or pyannote does not set it first |
| 8 | 2026-10-20 | Code review of `pyannote.audio` 4.0.7 (P3.4) | Usage telemetry is on by default: OpenTelemetry spans to `https://otel.pyannote.ai/v1/traces` on every model and pipeline load and on every file processed (duration, speaker counts, a session id). No audio, but data leaves India without a decision (golden rule 12). It uses its own tracer provider, so the app's own traces are not sent | medium | fixed | P3.4: `sabha_asr/diarization.py` sets `PYANNOTE_METRICS_ENABLED=false` and `HF_HUB_DISABLE_TELEMETRY=1` before pyannote is imported, and loads the model from a local folder with `HF_HUB_OFFLINE=1`. A test fails if other code imports pyannote. Network checked with strace (see the P3.4 commit) |
| 9 | 2026-10-21 | `pip-audit` in CI | [PYSEC-2026-4320](https://osv.dev/vulnerability/PYSEC-2026-4320) / GHSA-6q48-6c7w-9gw2: `certifi` 2026.7.22 trusts the `emSign ECC Root CA - G3`, under which eight intermediate CAs had their private keys compromised (anyone holding one can impersonate any HTTPS site to clients using certifi: requests, httpx, boto3) | high | fixed | certifi 2026.10.19, which removes the emSign roots. Our workers call Sarvam, OpenAI and S3 over HTTPS |
| 10 | 2026-10-21 | `pnpm audit` in CI | [GHSA-587h-7wmj-h5pm](https://github.com/advisories/GHSA-587h-7wmj-h5pm): `vite` 8.3.0–8.3.2 (via `launch-editor`): the dev server's file-existence check can be bypassed on Windows | high | fixed | vite 8.3.3 (released 2026-10-06). Development server only; the built site never includes it |
| 11 | 2026-10-22 | `pip-audit` in CI | [CVE-2026-113722](https://osv.dev/vulnerability/CVE-2026-113722): `virtualenv` 21.14.7 writes console-script launchers whose interpreter path is still shell-expanded, so someone who controls where an environment is created could run commands. Pulled in only by `pre-commit` on developer machines; never in the product | low | fixed | virtualenv 21.14.9 (released 2026-10-17) |
| 12 | 2026-10-24 | `pip-audit` in CI | Six advisories in `filelock` 4.1.1 (CVE-2026-112906, -112907, -112913, -112914, -112937, -112940), published after PR #8 was opened | not rated here | fixed | filelock 4.2.1 (released 2026-10-17), the lowest fixed version |
| 13 | 2026-10-24 | `pip-audit` in CI | CVE-2026-114603 in `opentelemetry-api` 1.45.0 | not rated here | fixed | OpenTelemetry 1.45.1 / 0.66b1 as one set (released 2026-10-06); the pins in `packages/core`, `packages/llm` and `apps/api` widened by one patch release |
| 14 | 2026-10-24 | `pip-audit` in CI | CVE-2026-113713 in `virtualenv` 21.14.9 (developer machines only, via `pre-commit`) | low | fixed | virtualenv 21.14.10 (released 2026-10-17), the lowest fixed version |
| 15 | 2026-10-24 | `pnpm audit` in CI | [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) (`zod` via `eslint-plugin-react-hooks`) and [GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c) (`undici` via `jsdom`) | high | zod closed 2026-10-28; undici accepted until 2026-10-29 | Development tools only (lint, unit-test DOM); nothing ships to browsers. Their fixes are younger than the 14-day install rule, so they are ignored in `package.json` until they qualify: zod on 2026-10-25, undici on 2026-10-29. Listed in `apps/web/README.md`. **Zod closed 2026-10-28**: updated to 4.6.7 (lockfile only, within `eslint-plugin-react-hooks`' range) and the ignore removed |
| 16 | 2026-10-28 | `pnpm audit` in CI | [GHSA-4w7w-5xrc-9h26](https://github.com/advisories/GHSA-4w7w-5xrc-9h26), [GHSA-2m5v-pch6-74hx](https://github.com/advisories/GHSA-2m5v-pch6-74hx), [GHSA-qrxm-fqhp-jwvm](https://github.com/advisories/GHSA-qrxm-fqhp-jwvm) (`undici` via `jsdom`; TLS validation bypass, TLS 1.2 renegotiation DoS) | high | accepted until 2026-10-29 | Unit-test DOM only; nothing ships to browsers and tests make no TLS connections to untrusted servers. The fix (undici 8.12.2, via jsdom 30.1.3) was published 2026-10-15 and passes the 14-day install rule on 2026-10-29; ignored in `package.json` until then. Listed in `apps/web/README.md` |

### Reviewed in code (no finding)

| Area | Where | Note |
| --- | --- | --- |
| JWT validation | `apps/api/sabha_api/auth/oidc.py` | RS256 only, issuer, audience, expiry, key rotation; algorithm-confusion and unsigned tokens refused (tests) |
| Tenant isolation | `packages/core/sabha_core/repo.py`, `docs/security/permissions.yaml` | Every route was checked as nine callers against `permissions.yaml` until the tests were removed (2026-11-19); now the matrix is a written record only |
| Presigned URLs | `apps/api/sabha_api/services/recordings.py` | Upload parts only, 15-minute expiry, keys always under `{tenant_id}/` |
| ffmpeg input | `apps/workers/sabha_workers/stages/preprocess.py` | `-protocol_whitelist file` on every ffmpeg and ffprobe input, so a crafted file cannot make them fetch other addresses |
| Error messages | `apps/api/sabha_api/errors.py` | problem+json; unexpected errors become a generic 500 without internals |

### Not run yet

| Check | Needs |
| --- | --- |
| OWASP ZAP baseline scan (authenticated) | Staging (P1.3) |
| trivy on the published images | Published images; there is no CI ([ADR 0010](#doc-docs-adr-0010-no-github-actions-md)), so run it by hand |
| S3 bucket policies, IAM least privilege | The AWS account and Terraform (P1.3) |
| SSRF guard for webhook URLs | Webhooks (P2.7, not built yet) |
| Secrets rotation procedure | The runbook (P7.7) |

<a id="doc-docs-security-permissions-yaml"></a>

## permissions.yaml

*Source: [`docs/security/permissions.yaml`](security/permissions.yaml)*

```yaml
# Who may call what: the permission matrix for every API route (plan task P7.4).
#
# Reviewed by the owner on 2026-10-19. Until 2026-11-19 a test called every route as every caller against this file;
# the tests were removed then (docs/adr/0016-no-automated-tests.md), so it is now the written record only. Add every
# new route here by hand, with the decision of who may call it.
#
# Callers. Tenant A has units unit-1 and unit-2. The target recording (for routes with {recording_id}) belongs to
# tenant A, unit-1, person "Asha" (linked to staff_uploader), and was uploaded by staff_uploader.
#   anonymous            no token
#   owner, admin         tenant A
#   manager_unit         tenant A manager of unit-1 (the recording's unit)
#   manager_other_unit   tenant A manager of unit-2
#   reviewer_unit        tenant A reviewer of unit-1
#   staff_uploader       tenant A staff, the person analysed, who uploaded the recording
#   staff_colleague      tenant A staff, someone else
#   other_tenant         owner of tenant B
#
# Statuses are what the caller gets. 404 (not 403) for a recording the caller may not see, so its existence is not
# revealed.

callers:
  - anonymous
  - owner
  - admin
  - manager_unit
  - manager_other_unit
  - reviewer_unit
  - staff_uploader
  - staff_colleague
  - other_tenant

routes:
  GET /health:
    # Load balancers and the deploy script; never touches a dependency.
    all: 200

  GET /ready:
    # Public like /health; 503 while a dependency is down, never 401/403.
    all: [200, 503]

  GET /v1/meta:
    all: 200

  GET /v1/me:
    anonymous: 401
    others: 200  # each caller sees only themselves and their own tenant

  POST /v1/users/invites:
    # Body: a new user with role "staff". Owners invite any role; admins manager, reviewer and staff (2026-10-19).
    anonymous: 401
    owner: 201
    admin: 201
    manager_unit: 403
    manager_other_unit: 403
    reviewer_unit: 403
    staff_uploader: 403
    staff_colleague: 403
    other_tenant: 201  # creates the user in tenant B, never in tenant A

  POST /v1/users/invites (admin inviting an admin):
    anonymous: 401
    owner: 201
    admin: 403  # role_not_allowed
    manager_unit: 403
    manager_other_unit: 403
    reviewer_unit: 403
    staff_uploader: 403
    staff_colleague: 403
    other_tenant: 201

  POST /v1/recordings:
    # Body: a teaching recording for person Asha (staff_uploader's person).
    anonymous: 401
    owner: 201
    admin: 201
    manager_unit: 201
    manager_other_unit: 403  # managers and reviewers upload only for people in their units (person_not_allowed)
    reviewer_unit: 201
    staff_uploader: 201  # staff upload only for their own person
    staff_colleague: 403  # person_not_allowed
    other_tenant: 422  # unknown_person: Asha is not in tenant B

  POST /v1/recordings/{recording_id}/parts:
    # Fresh part URLs to resume an upload still in progress.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 404  # only the uploader, owners and admins resume an upload
    manager_other_unit: 404
    reviewer_unit: 404
    staff_uploader: 200
    staff_colleague: 404
    other_tenant: 404

  POST /v1/recordings/{recording_id}/complete:
    # Finishing an upload; same rule as /parts.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 404
    manager_other_unit: 404
    reviewer_unit: 404
    staff_uploader: 200
    staff_colleague: 404
    other_tenant: 404

  GET /v1/recordings:
    # The caller's visible recordings (P5.7b); each caller gets a list, filtered (tested in apps/api/tests).
    anonymous: 401
    others: 200

  GET /v1/recordings/{recording_id}:
    # Reads (P5.7b): owners and admins all; managers and reviewers their units; staff their own (2026-10-19).
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # managers and reviewers see their units only
    reviewer_unit: 200
    staff_uploader: 200  # staff see their own person's recordings
    staff_colleague: 404
    other_tenant: 404

  GET /v1/recordings/{recording_id}/transcript:
    # Same rule; issuing the playback URL is audited (recording.play).
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # managers and reviewers see their units only
    reviewer_unit: 200
    staff_uploader: 200  # staff see their own person's recordings
    staff_colleague: 404
    other_tenant: 404

  GET /v1/recordings/{recording_id}/analysis:
    # Same rule; audited (analysis.view). Evidence is redacted for everyone (2026-10-19).
    # Coaching (strengths, gaps, suggestions) is private to the person analysed (founder, 2026-11-12): everyone
    # else gets 200 with them empty and coaching_private true (apps/api/tests/test_results.py).
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # managers and reviewers see their units only
    reviewer_unit: 200
    staff_uploader: 200  # staff see their own person's recordings
    staff_colleague: 404
    other_tenant: 404

  GET /v1/recordings/{recording_id}/analyses:
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # managers and reviewers see their units only
    reviewer_unit: 200
    staff_uploader: 200  # staff see their own person's recordings
    staff_colleague: 404
    other_tenant: 404

  GET /v1/people/{person_id}/trend:
    # The target person is Asha (unit-1, linked to staff_uploader).
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # managers and reviewers see their units only
    reviewer_unit: 200
    staff_uploader: 200  # staff see their own person's recordings
    staff_colleague: 404
    other_tenant: 404

  GET /v1/people:
    # The people each caller may see and upload for (filtered; tested in apps/api/tests/test_results.py).
    anonymous: 401
    others: 200

  PUT /v1/recordings/{recording_id}/voices:
    # Meetings: naming the anonymous voices, display only; a fresh meeting of Asha's per call. Audited.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # not their unit
    reviewer_unit: 200
    staff_uploader: 200  # their own recording
    staff_colleague: 404
    other_tenant: 404

  GET /v1/reviews:
    # Recordings waiting for a person's decision (ADR 0007); filtered like the recordings list.
    anonymous: 401
    staff_uploader: 403  # staff never resolve reviews, not even their own
    staff_colleague: 403
    others: 200

  GET /v1/recordings/{recording_id}/speakers:
    # Who spoke how much, with sample lines, for a reviewer to say who is who.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404  # not their unit
    reviewer_unit: 200
    staff_uploader: 403  # staff never resolve reviews
    staff_colleague: 403
    other_tenant: 404

  POST /v1/recordings/{recording_id}/review:
    # Confirm the roles (then it is scored) or close as not usable; a fresh recording in review per call. Audited.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404
    reviewer_unit: 200
    staff_uploader: 403  # never their own
    staff_colleague: 403
    other_tenant: 404

  GET /v1/overview:
    # Numbers for the recordings each caller may see (filtered; tested in apps/api/tests/test_results.py).
    anonymous: 401
    others: 200

  GET /v1/costs/estimate:
    # Expected cost of an upload in rupees (owner, 2026-10-28: every role sees costs); this organisation's history.
    anonymous: 401
    others: 200

  GET /v1/speech-models:
    # The speech-to-text models an upload may choose, with prices (owner, 2026-11-13). Only owners and admins may
    # choose one (POST /v1/recordings refuses others), but the list holds nothing private.
    anonymous: 401
    others: 200

  GET /v1/recordings/{recording_id}/cost:
    # Expected and actual cost of one recording, for anyone who may see it (every role, owner 2026-10-28).
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404
    reviewer_unit: 200
    staff_uploader: 200
    staff_colleague: 404
    other_tenant: 404

  POST /v1/units:
    # Classes and sections (owner, 2026-10-28): owners and admins only. A fresh section under unit-1 per call;
    # other_tenant has no unit-1 (422 unknown_unit).
    anonymous: 401
    owner: 201
    admin: 201
    other_tenant: 422
    others: 403

  PATCH /v1/units/{unit_id}:
    # Rename a unit of tenant A, made fresh per call; other_tenant cannot see it (404).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  POST /v1/people:
    # Add a teacher (a record, no login; owner 2026-10-28): owners and admins. other_tenant has no unit-1 (422).
    anonymous: 401
    owner: 201
    admin: 201
    other_tenant: 422
    others: 403

  PATCH /v1/people/{person_id}:
    # Change a teacher's units; a fresh person of tenant A per call, which other_tenant cannot see (404).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  GET /v1/inbox:
    # The bell and "Needs your decision" (UI v2): only what each caller may act on (filtered; test_results.py).
    anonymous: 401
    others: 200

  GET /v1/search:
    # Header search by name (UI v2): only what each caller may see (filtered; tested in apps/api/tests/test_results.py).
    anonymous: 401
    others: 200

  GET /v1/people/summary:
    # The People page: the same people as GET /v1/people, with counts and scores (filtered; test_results.py).
    anonymous: 401
    others: 200

  POST /v1/analyses/{analysis_id}/disputes:
    # Ask a reviewer to look at one score (P6.7, owner's decisions 2026-10-26): the person analysed, the managers of
    # their unit, owners and admins. A fresh analysis of Asha's per call. Audited.
    anonymous: 401
    owner: 201
    admin: 201
    manager_unit: 201
    manager_other_unit: 404  # cannot see it
    reviewer_unit: 403  # sees it, but reviewers decide disputes rather than raise them
    staff_uploader: 201  # her own score
    staff_colleague: 404
    other_tenant: 404

  GET /v1/disputes:
    # The reviewer's queue of disputes, filtered to the units each caller may see; staff never resolve.
    anonymous: 401
    staff_uploader: 403
    staff_colleague: 403
    others: 200

  POST /v1/disputes/{dispute_id}/resolve:
    # Accept (with the final score) or reject, with a note: reviewers and managers for their units, owners and admins
    # for all, never a dispute you raised yourself. A fresh dispute raised by Asha per call. Audited.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 200
    manager_other_unit: 404
    reviewer_unit: 200
    staff_uploader: 403  # she raised it, and staff never resolve
    staff_colleague: 403
    other_tenant: 404

  POST /v1/recordings/{recording_id}/reanalyze:
    # Score a finished recording again from its transcript (P2.8, owner's decision 2026-10-26: owners and admins;
    # each run costs an LLM scoring). A fresh finished recording of Asha's per call. Audited.
    anonymous: 401
    owner: 200
    admin: 200
    manager_unit: 403  # sees it, but re-analysis is for owners and admins
    manager_other_unit: 404
    reviewer_unit: 403
    staff_uploader: 403
    staff_colleague: 404
    other_tenant: 404

  POST /v1/reanalysis:
    # Re-analyse every finished recording of a type scored with an older rubric (count first, at most 100 per
    # request). Called with dry_run, so it only counts; other_tenant counts its own tenant's (none).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 200
    others: 403

  GET /v1/events:
    # Live status (P2.6): every signed-in caller may listen; each receives only events about recordings they may
    # see (tested in apps/api/tests/test_events.py). The matrix runs without Redis, so the route answers 503 and
    # the web app keeps polling.
    anonymous: 401
    others: [200, 503]

  GET /v1/settings:
    # Workspace settings (P1.7): owners and admins ("Admins can rename any of these in Settings", the setup design).
    # Everyone else reads the labels from /v1/me. other_tenant reads its own tenant's.
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 200
    others: 403

  PATCH /v1/settings:
    # Body: rename the person label. other_tenant renames its own tenant's (apps/api/tests/test_settings.py checks
    # tenant A is untouched).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 200
    others: 403

  GET /v1/usage:
    # This month's audio hours against the plan (the sidebar's plan block): owners and admins. other_tenant sees its
    # own tenant's.
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 200
    others: 403

  GET /v1/recordings/export.csv:
    # "Export list" (UI v2, owner's decision 2026-11-03): the caller's visible recordings as CSV, filtered like the
    # list. Audited as recordings.export.
    anonymous: 401
    others: 200

  POST /v1/recordings/share:
    # Share reports with the people analysed (UI v2, 2026-11-03): an email and a note; access does not change.
    # Everyone but staff; ids the caller cannot see are skipped silently (manager_other_unit and other_tenant share
    # nothing), so the answer is 200 with an empty list rather than 404.
    anonymous: 401
    staff_uploader: 403
    staff_colleague: 403
    others: 200

  GET /v1/recordings/counts:
    # Recordings per conversation type for the sidebar: every signed-in caller, counting only what they may see
    # (apps/api/tests/test_usage.py).
    anonymous: 401
    others: 200

  GET /v1/rubrics:
    # The rubrics of the tenant's conversation types, read-only: everyone signed in, staff included, so they can see
    # how they are scored (owner's decision, 2026-10-27).
    anonymous: 401
    others: 200

  GET /v1/rubrics/{rubric_id}:
    # The school's teaching rubric. other_tenant is a school too, so reads the same file (rubrics are product
    # content, not tenant data); a profile without it gets 404 (apps/api/tests/test_rubrics.py).
    anonymous: 401
    others: 200

  GET /v1/product-info:
    # Approved product information (founder's dashboard doc, 2026-11-12): everyone signed in reads the active
    # entries (reps review what coaching points them to).
    anonymous: 401
    others: 200

  POST /v1/product-info:
    # Only owners and admins (the doc's Super Admin) add entries. Audited.
    anonymous: 401
    owner: 201
    admin: 201
    other_tenant: 201  # its own tenant's list
    others: 403

  PATCH /v1/product-info/{entry_id}:
    # Change or retire an entry of tenant A, made fresh per call; other_tenant cannot see it (404).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  GET /v1/me/next-actions:
    # The caller's OWN next actions (founder's dashboard doc, 2026-11-12): only their linked person's data, so every
    # signed-in caller gets 200 (an empty list without a linked person).
    anonymous: 401
    others: 200

  GET /v1/me/summary:
    # The caller's OWN call and meeting counts and average score (zeros without a linked person).
    anonymous: 401
    others: 200

  GET /v1/me/coaching:
    # The caller's OWN private coaching: theme scores and practice points (empty without a linked person).
    anonymous: 401
    others: 200

  GET /v1/audit:
    # The audit log (P1.8): owners and admins only (owner's decision, 2026-10-27). other_tenant reads its own.
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 200
    others: 403

  POST /v1/recordings/{recording_id}/retry:
    # P7.8: owners and admins retry a failed recording (owner's decision, 2026-10-27): a fresh one of Asha's that
    # failed in transcription, per call. other_tenant cannot see it (404).
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  POST /v1/recordings/{recording_id}/abandon:
    # P7.8: owners and admins close a failed recording for good. Same target and outcomes as retry.
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  GET /v1/recordings/{recording_id}/processing:
    # P7.8: stage runs, the latest failure and the recorded AI cost, for owners and admins.
    anonymous: 401
    owner: 200
    admin: 200
    other_tenant: 404
    others: 403

  POST /v1/erasure:
    # P7.3: owners only (owner's decision, 2026-10-27). Called without confirm (a count), on Asha's recording;
    # other_tenant cannot see it (404).
    anonymous: 401
    owner: 200
    other_tenant: 404
    others: 403
```

<a id="doc-docs-design-tokens-md"></a>

## Design tokens

*Source: [`docs/design/tokens.md`](design/tokens.md)*

**UI v2 (since 2026-10-27).** Colours and the font come from the v2 screens in `docs/design/v2/` (`01-overview.png`,
`02-recordings.png`, `03-lesson-report.png`, `04-sales-report.png`, `05-reviews.png`, rendered from the designer's
PDF, which is too large for the repository). The owner gave the main values; tints and bar colours were sampled from
the PDF's pixels. Sizes, radii, spacing and the focus ring below are still the v1
values from `docs/design/source/*.dc.html` (`File:line`) until a page's v2 restyle changes them.

`apps/web/tailwind.config.ts` maps these tokens one to one. Change a value here first, then in the config.

### Colour

Text on every background below meets WCAG AA (4.5:1) for normal text.

**Light and dark (2026-11-12).** The values below are the light theme. Every token is a CSS variable set in
`apps/web/src/theme.css` for light and for dark (`<html data-theme="dark">`); `tailwind.config.ts` only names them.
Change a colour there, in both themes; `src/test/contrast.test.ts` checks the text pairs in each. Two tokens exist
for dark mode's sake: `on-primary` (text on a primary background: white in light, deep ink in dark, where primary is
lighter) and `scrim` (the layer behind a dialog, used as `bg-scrim/40`). Never put `text-surface` on `bg-primary`.
The device setting picks the theme until the person uses the sun/moon button in the top bar; the pick is kept in
this browser.

#### Text and neutrals

| Token | Hex | Used for |
| --- | --- | --- |
| `ink` | `#121521` | Primary text, headings, numbers; the signed-in person's avatar |
| `ink-2` | `#3D414C` | Nav items, table cells, secondary text on white |
| `ink-raised` | `#262B3E` | Chips on an ink surface (the sales report's "Next step agreed" card) |
| `muted` | `#5F6677` | Labels, subtitles, table headers, captions |
| `muted-2`, `subtle` | `#686F7F` | Quieter meta text, icons, counts |
| `line` | `#E4E7EC` | Panel borders, sidebar border, empty score-dash segments |
| `line-input` | `#D7D8DC` | Input and secondary-button borders |
| `line-strong` | `#B8BDC7` | Dashed drop-zone borders |
| `line-subtle` | `#ECEEF2` | Dividers inside panels |
| `track` | `#EEF0F3` | Bar tracks; the speaker strip where nobody speaks |
| `fill`, `fill-2` | `#F1F2F5`, `#E9EBEF` | Segmented-control background, timeline section labels |
| `surface` | `#FFFFFF` | Panels, sidebar, inputs |
| `surface-subtle` | `#F6F7F9` | Plan block, metric cards inside panels, timeline lanes |
| `surface-faint` | `#FAFBFC` | Unselected option cards |
| `page` | `#F6F7F9` | Page ground behind panels |

#### Primary and speakers

One blue (owner, 2026-10-27): the primary colour is also the staff speaker's colour.

| Token | Hex | Used for |
| --- | --- | --- |
| `primary` | `#3346D3` | Primary button, links, focus ring, active nav text, Reviews badge |
| `primary-hover` | `#2536B0` | Hover; text on primary tints |
| `primary-tint` | `#EEF0FC` | Active nav background, org mark, "Try next time" box |
| `primary-tint-subtle` | `#F5F5FD` | Selected list item |
| `primary-tint-strong` | `#DDE2F8` | Stronger tint |
| `primary-border` | `#B9C1F0` | Selected option-card border |
| `primary-disabled`, `primary-disabled-ink` | `#C9CEF2`, `#2F3A86` | Disabled primary button |
| `speaker-staff` | `#3346D3` | The analysed staff member in SpeakerStrip and the logo |
| `speaker-other` | `#F2A33A` | Everyone else (students, client, visitor); also `brand-accent` in the logo |

#### Score tones and status

| Token | Hex | Used for |
| --- | --- | --- |
| `success` | `#0B6343` | Good-band score text, positive deltas, "Ready" |
| `success-bar` | `#1F9A6B` | Score dashes and bars in the good band |
| `success-tint` | `#DDF1E6` | Good-band chips and heatmap cells, "Handled" |
| `warning`, `warning-ink` | `#7A4A00` | Mid-band score text, "Disputed", "Needs review", other-speaker labels |
| `warning-bar` | `#E8A23F` | Score dashes in the mid band |
| `warning-tint` | `#FCEBCF` | Mid-band chips and heatmap cells |
| `warning-tint-subtle` | `#FEF6E9` | Softer amber fill |
| `warning-surface` | `#FEFAF1` | Quote boxes on the deal card, highlighted transcript lines, the proposer's card |
| `warning-border` | `#ECD9B8` | Border of those boxes |
| `danger` | `#A12B12` | Low-band score text, errors, "Failed", "Open" |
| `danger-bar` | `#DB532E` | Score dashes in the low band |
| `danger-tint` | `#FBE2DB` | Low-band chips and heatmap cells |

#### Conversation types

| Token | Hex | Type |
| --- | --- | --- |
| `type-teaching` | `#3346D3` | Teaching (same as `primary`) |
| `type-reception` | `#F2A33A` | Reception |
| `type-counselling` | `#1E7A55` | Counselling |
| `type-meeting` | `#7A4DB8` | Meetings |
| `type-sales` | `#0F7C8C` | Sales |
| `type-support` | `#C2417A` | Support (added 2026-11-04; no design mockup, chosen to stay apart from the others) |

### Typography

**Family:** `Geist, 'Segoe UI', system-ui, sans-serif` (UI v2). The app self-hosts it with `@fontsource/geist`, so
pages make no requests to an outside font service.

**Weights:** 400, 500, 600, 700 (`Main.dc.html:10`). 600 is the workhorse for emphasis (143 uses across the
sources), 700 for the page title, wordmark and avatar initials, 500 for table headers and suffixes.

**Base:** 14px, line-height 1.45, `font-variant-numeric: tabular-nums` on the whole page (`Main.dc.html:18`).

| Token | Size | Line height / tracking | Used for | Source |
| --- | --- | --- | --- | --- |
| `2xs` | 11px | — | Speaker badge initials | `Analysis.dc.html:149` |
| `xs` | 11.5px | — | Section labels in setup, timeline ticks | `Setup.dc.html:95`, `Analysis.dc.html:160` |
| `caption` | 12px | — | Meta text, counts, badges, stage notes | `Main.dc.html:33`, `:51`, `:143` |
| `small` | 12.5px | — | Deltas, table headers, person line, chips | `Main.dc.html:112`, `:166`, `:187` |
| `sm` | 13px | — | Labels, secondary body, segmented buttons | `Main.dc.html:110`, `:155` |
| `table` | 13.5px | — | Table body, coaching list | `Main.dc.html:164`, `:210` |
| `base` | 14px | 1.45 | Body | `Main.dc.html:18` |
| `md` | 15px | — | Option-card titles | `Setup.dc.html:55` |
| `lg` | 16px | — | Panel headings (h2) | `Main.dc.html:133` |
| `brand` | 17px | -0.01em | Wordmark | `Main.dc.html:28` |
| `xl` | 18px | — | Large panel headings | `Upload.dc.html:93`, `Rubrics.dc.html:156` |
| `2xl` | 20px | — | Stage counts, small metrics | `Main.dc.html:141` |
| `3xl` | 24px | -0.015em | Plan names | `Plans.dc.html:85` |
| `title` | 26px | 1.2 / -0.015em | Page title (h1) | `Main.dc.html:88` |
| `metric` | 28px | -0.02em | Metric-strip numbers | `Main.dc.html:111` |
| `hero` | 44px | 1 / -0.03em | Report headline score | `Analysis.dc.html:102` |

### Radii

| Token | Value | Used for | Source |
| --- | --- | --- | --- |
| `xs` | 2px | Type swatches, logo bars | `Main.dc.html:64` |
| `sm` | 3px | Legend swatches | `Analysis.dc.html:133` |
| `md` | 6px | Waveform, timeline | `Analysis.dc.html:154` |
| `seg` | 7px | Segmented-control buttons | `Main.dc.html:155` |
| `DEFAULT` | 8px | Buttons, inputs, nav items, logo | `Main.dc.html:30`, `:92`, `:101` |
| `seg-outer` | 9px | Segmented-control track | `Main.dc.html:154` |
| `card` | 10px | Stage cards, plan card | `Main.dc.html:70`, `:138` |
| `panel` | 12px | Panels | `Main.dc.html:108`, `:131` |
| `full` | 999px | Chips, badges, avatars, progress bars | `Main.dc.html:51`, `:72`, `:187` |

### Spacing

The sources use a 2px-based scale. The common steps (by number of uses) are 2, 4, 6, 8, 10, 12, 14, 16, 18, 20,
24, 28, 40 and 48 px. Tailwind's default 4px scale covers most of these; the config adds `0.5` → 2px (default),
`1.5` → 6px (default), `2.5` → 10px (default), `3.5` → 14px (default), `4.5` → 18px (added) so the odd steps
need no arbitrary values.

| Where | Value | Source |
| --- | --- | --- |
| Sidebar padding | 20px 14px | `Main.dc.html:20` |
| Sidebar width | 232px | `Main.dc.html:20` |
| Main padding | 28px clamp(16px, 3vw, 40px) 48px | `Main.dc.html:84` |
| Gap between main sections | 24px | `Main.dc.html:84`, `:149` |
| Panel padding | 18px 20px | `Main.dc.html:109`, `:131` |
| Table cell padding | 12px (20px at row ends) | `Main.dc.html:178` |
| Header control gap | 10px | `Main.dc.html:91` |

### Focus ring

`outline: 2px solid #3346D3; outline-offset: 2px` (`primary`) on `:focus-visible` for buttons, links, inputs,
selects and textareas, plus `label:focus-within` for the upload zone and `label:has(input[type=radio]:focus-visible)` for
option cards. Source: line 15 of every design file (`Main.dc.html:15`, `Upload.dc.html:15`,
`Setup.dc.html:15-16`).

### Touch size

Minimum touch target **44px**. In the designs, header inputs and buttons, the campus switcher and primary
actions are 44px (`Main.dc.html:30`, `:92`, `:97`, `:101`).

**Gap in the designs:** nav rows are 40px (`Main.dc.html:38`), conversation-type rows 36px (`:64`) and
segmented-control buttons 32px (`:155`). These are below 44px. The spike matches the design; P6.1 needs a
decision (raise them to 44px, or accept them as desktop-only).

### Status chips

Still the v1 pill until the Recordings restyle (v2 shows a dot and coloured text with no background,
`02-recordings.png`): `padding 3px 9px`, radius `full`, 12.5px / 600, with a 6px dot in the text colour
(`Main.dc.html:187`).
The token names are unchanged, so the hex values below are the v2 ones.

| Status | Text | Background |
| --- | --- | --- |
| Analysed | `success` `#0B6343` | `success-tint` `#DDF1E6` |
| Transcribing, Analysing, Uploading | `primary-hover` `#2536B0` | `primary-tint` `#EEF0FC` |
| Needs review | `warning-ink` `#7A4A00` | `warning-tint` `#FCEBCF` |
| Failed | `danger` `#A12B12` | `danger-tint` `#FBE2DB` |
| Live (rubric) | `success` | `success-tint` |
| Calibrating (rubric) | `warning-ink` | `warning-tint` |

Badge (nav count, UI v2): `min-width 22px`, `padding 1px 7px`, radius `full`, 12px / 600, white on `primary`.

**Box sizing:** the design files leave most elements at the browser default (`content-box`); only the sidebar,
main area and a few wrappers set `border-box`. Tailwind uses `border-box` everywhere, so a padded element with a
`min-width` renders smaller unless the padding is added in: the badge above is 36px wide in the screenshot
(22 + 7 + 7). The search field in the header is 46px tall in the screenshot (44px + 1px borders); the app keeps
it at the 44px token.

Type marker: 8×8px square, radius `xs`, in the type colour (`Main.dc.html:64`, `:183`).

### Score colour bands

UI v2 rule (owner, 2026-10-27; the coaching legend in `v2/01-overview.png`), in `apps/web/src/design/score.ts`:

| Low (`danger`) | Mid (`warning`) | Good (`success`) |
| --- | --- | --- |
| below 3.0 | 3.0 to 3.79 | 3.8 and above |

The cut is on the one-decimal value people see, so 3.75 (shown as 3.8) is good. It replaces the v1 rule (good
from 4.0).

<a id="doc-docs-setup-auth-md"></a>

## Setting up sign-in (Auth0)

*Source: [`docs/setup/auth.md`](setup/auth.md)*

Sabha signs people in with Auth0 (docs/adr/0002-auth.md). Auth0 only checks who someone is. Their tenant, role and
units come from Sabha's own records, and people can use Sabha only after an owner or admin invites them (P1.5b).
These steps are done once per environment (dev, staging, production), in a separate Auth0 tenant for each.

### 1. Create the Auth0 tenant

1. Sign up at auth0.com and create a tenant per environment, for example `sabha-dev`.
2. Pick the region when you create the tenant: it cannot be changed later. The owner approved storing staff
   names and emails outside India on 2026-10-16 (ADR 0002). Note the region you picked in the ADR.
3. The issuer is `https://<tenant>.<region>.auth0.com/` (shown as "Domain" on any application, add `https://`).

### 2. Register the API

Applications → APIs → Create API:

| Field | Value |
| --- | --- |
| Name | Sabha API |
| Identifier | e.g. `https://api.sabha.dev`. This is the audience. It is a name, not a URL Auth0 calls, and it cannot be changed later |
| Signing algorithm | RS256 (the API refuses anything else) |

In the API's settings, turn on **Allow Offline Access**. Without it Auth0 issues no refresh tokens, and people are
signed out when their access token expires.

### 3. Register the web app

Applications → Applications → Create Application → **Single Page Web Applications**. In its settings:

| Field | Dev value | Staging/production |
| --- | --- | --- |
| Allowed Callback URLs | `http://localhost:5180/` | `https://<web host>/` |
| Allowed Logout URLs | `http://localhost:5180/` | `https://<web host>/` |
| Allowed Web Origins | `http://localhost:5180` | `https://<web host>` |
| Refresh Token Rotation | On | On |

Note its **Client ID**. A single-page app has no client secret.

### 4. Google login

Authentication → Social → Google, and enable it for the web app (the application's Connections tab).

- In dev you can use Auth0's development keys for Google.
- For staging and production, create an OAuth client in Google Cloud (OAuth consent screen, then Credentials →
  OAuth client ID, type "Web application"). Add `https://<tenant domain>/login/callback` as an authorised redirect
  URI and paste its client ID and secret into the Auth0 Google connection.

Under Authentication → Database, either turn off the "Username-Password-Authentication" connection for the web app
or disable sign-ups on it. Uninvited people are refused by the API anyway (403 `not_invited`), but there is no
reason to let them create provider accounts.

### 5. Sign-out

The web app signs out with the standard OIDC end-session endpoint. Check that
`https://<tenant domain>/.well-known/openid-configuration` lists `end_session_endpoint`. If it does not, turn on
RP-Initiated Logout in the tenant's advanced settings.

### 6. Configure Sabha

Root `.env` (API):

```
OIDC_ISSUER=https://<tenant domain>/
OIDC_AUDIENCE=<API identifier from step 2>
OIDC_CLIENT_ID=<Client ID from step 3>
```

`apps/web/.env.local` for `pnpm dev`, or `--build-arg` for the web image (see `apps/web/.env.example`):

```
VITE_OIDC_AUTHORITY=https://<tenant domain>/
VITE_OIDC_CLIENT_ID=<Client ID from step 3>
VITE_OIDC_AUDIENCE=<API identifier from step 2>
```

In staging and production, add `https://<tenant domain>` to the web container's `CSP_CONNECT_SRC`, or the browser
blocks sign-in and token renewal.

### Checking it works

1. Create a tenant and invite yourself as its owner, with the email of the Google account you will sign in with:
   `uv run python scripts/admin/create_tenant.py --name "Test School" --owner-email you@example.com --owner-name "You"`.
2. `make api` and `pnpm -C apps/web dev`, then open http://localhost:5180/. You should be sent to Auth0, sign in
   with Google, and come back to Sabha.
3. `GET /v1/me` with your access token returns your role (owner) and your tenant's labels. Your first sign-in
   links the invite to your login and marks you active.

Owners and admins invite everyone else with `POST /v1/users/invites` (owners any role; admins manager, reviewer
and staff). People sign in with the invited email; an unverified email, or invites from two organisations, are
refused with a clear error.

<a id="doc-docs-setup-cloud-checklist-md"></a>

## Cloud setup checklist

*Source: [`docs/setup/cloud-checklist.md`](setup/cloud-checklist.md)*

Plan task 0.5. For a person to work through by hand in the cloud consoles; nothing here is automated. Terraform
(plan task 1.3) takes over the AWS parts later, so keep the names you choose here.

Rules that apply throughout (from `CLAUDE.md`):

- **Data stays in India** (golden rule 12). Every resource that stores or processes customer data goes in AWS
  `ap-south-1` (Mumbai) or Atlas AWS Mumbai. Anything that would put data elsewhere needs an explicit decision
  first; this list marks those places.
- **Secrets only in environment variables or a secret store** (golden rule 11). Never paste a key, password or
  connection string into the repo, a ticket or chat. Record names and IDs here, never secrets.

Record as you go (no secrets):

| Item | Value |
| --- | --- |
| AWS account ID (staging) | |
| AWS account ID (production) | |
| S3 buckets (staging): audio / artefacts / backups | |
| S3 buckets (production): audio / artefacts / backups | |
| App IAM role ARN (staging / production) | |
| Atlas organisation / project | |
| Atlas cluster name (staging / production) | |
| GitHub organisation / repository | |
| Sentry organisation / project | |
| SES sending domain | |

---

### 1. AWS account

- [ ] Create the AWS account with a shared team mailbox (not a personal email) as the root user.
- [ ] Turn on MFA for the root user. Store the root credentials offline; do not use root day to day.
- [ ] Decide on account structure. Recommended: AWS Organizations with separate **staging** and **production**
      accounts, so a mistake in staging cannot touch production data.
- [ ] Set up IAM Identity Center for people (named users, MFA required). No long-lived access keys for humans.
- [ ] In each account, set the console default region to **Asia Pacific (Mumbai) `ap-south-1`**.
- [ ] Optional guard: a Service Control Policy that denies actions outside `ap-south-1` (exempt global services
      such as IAM, Organizations, Budgets and billing).
- [ ] Turn on CloudTrail (all regions, logs to a bucket in `ap-south-1`).

### 2. Billing alerts

Set the amounts from the approved pilot budget; this checklist deliberately does not suggest figures.

- [ ] AWS Budgets: one monthly cost budget per account, with email alerts at 50%, 80% and 100% of actual spend
      and at 100% of forecast spend, sent to the team mailbox.
- [ ] Turn on AWS Cost Anomaly Detection with an email subscription.
- [ ] MongoDB Atlas: billing alerts for the organisation (see section 5).
- [ ] Note who reviews the bill each month: ______

### 3. S3 buckets

Three buckets per environment, in `ap-south-1`, so each kind of data gets its own lifecycle and access rules.
Local development uses RustFS instead (`S3_ENDPOINT_URL`, ADR 0003). Terraform (plan task 1.3) will codify this
section.

| Bucket | Setting | Holds |
| --- | --- | --- |
| `sabha-<env>-audio-<suffix>` | `S3_BUCKET_AUDIO` | Uploaded originals |
| `sabha-<env>-artefacts-<suffix>` | `S3_BUCKET_ARTEFACTS` | Pipeline outputs: derived audio, transcripts, analyses |
| `sabha-<env>-backups-<suffix>` | `S3_BUCKET_BACKUPS` | Database backups (plan task 7.3) |

- [ ] Create the three buckets for staging and for production in `ap-south-1` (bucket names are global, so add a
      suffix).
- [ ] **Block Public Access:** turn on all four settings at the **account** level and on each bucket.
- [ ] **Object Ownership:** "Bucket owner enforced" (ACLs disabled).
- [ ] **Default encryption:** SSE-S3 (or SSE-KMS with a key in `ap-south-1` if you want key-level audit).
- [ ] **TLS only:** add a bucket policy that denies requests where `aws:SecureTransport` is `false`.
- [ ] **Lifecycle rules:**
  - [ ] *Audio bucket:* expire objects after 90 days (the default audio retention). Plan task 1.3 also moves them to
        Infrequent Access after 30 days.
  - [ ] *Artefacts bucket:* expire derived audio (normalised, compact and playback copies) after 90 days with a rule
        filtered by object tag `data-class=audio`; the preprocessing code (plan task 3.2) must set that tag.
  - [ ] *Audio bucket:* abort incomplete multipart uploads after 7 days. Browser uploads are multipart; abandoned
        ones otherwise keep costing storage.
  - [ ] *Backups bucket:* turn on versioning (plan task 1.3); retention is decided in plan task 7.3.
  - [ ] If you turn on versioning, also expire noncurrent versions after the same number of days, or deleted audio
        survives as old versions.
  - [ ] Retention for transcripts and reports: wait for the lawyer's answer (`docs/legal/drafts/`); do not add a
        rule yet.
- [ ] **CORS** (browsers upload directly with presigned URLs, golden rule 2): allow the web app origin only, methods
      `PUT` and `GET`, and expose the `ETag` header (multipart completion needs it).

```json
[
  {
    "AllowedOrigins": ["https://app.<your-domain>"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

### 4. IAM for the application

Prefer an **IAM role** attached to the compute (EC2 instance profile or ECS task role). The app then needs no
access keys: leave `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` empty and the AWS SDK picks up the role.

- [ ] Create role `sabha-app-<env>` in each account with only this policy (replace the placeholders):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOwnBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:ListBucketMultipartUploads"],
      "Resource": [
        "arn:aws:s3:::<audio-bucket>",
        "arn:aws:s3:::<artefacts-bucket>",
        "arn:aws:s3:::<backups-bucket>"
      ]
    },
    {
      "Sid": "ReadWriteOwnObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": [
        "arn:aws:s3:::<audio-bucket>/*",
        "arn:aws:s3:::<artefacts-bucket>/*",
        "arn:aws:s3:::<backups-bucket>/*"
      ]
    },
    {
      "Sid": "SendFromOurDomainInMumbai",
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "arn:aws:ses:ap-south-1:<account-id>:identity/<your-domain>"
    }
  ]
}
```

- [ ] Do not grant `s3:*`, bucket-policy or IAM permissions to the app.
- [ ] If an IAM **user** with access keys is unavoidable (for example, a server outside AWS), give it the same policy,
      keep the keys in the deployment's secret store, and rotate them at least every 90 days.

### 5. MongoDB Atlas (Mumbai)

- [ ] Create the Atlas organisation (team mailbox as owner, MFA on) and one project per environment.
- [ ] Create an **M10** cluster per environment on **AWS, Mumbai (`ap-south-1`)**, MongoDB **7**. Atlas clusters are
      replica sets, which Sabha needs for transactions and change streams.
- [ ] Turn on Cloud Backup; choose the snapshot schedule and retention with plan task 7.3.
- [ ] **Network access:** use a private endpoint or VPC peering to the app's VPC if possible. Otherwise add only the
      app servers' fixed IPs to the access list. Never `0.0.0.0/0`.
- [ ] **Database user** per environment: `readWrite` on the `sabha` database only, a generated password, stored in
      the secret store.
- [ ] Copy the `mongodb+srv://` connection string into the secret store as `MONGO_URI`.
- [ ] Atlas billing alerts for the organisation, sent to the team mailbox.

### 6. GitHub

GitHub hosts code, not customer data; keep it that way (no recordings, transcripts or real names in the repo).

- [ ] Create the GitHub organisation; require two-factor authentication for all members.
- [ ] Create the private repository `sabha` with default branch `main`, then push this repo.
- [ ] Ruleset on `main`: pull request required with at least one approval, required status checks (add them after
      plan task 1.2 creates CI), no force pushes, no deletion.
- [ ] Turn on Dependabot alerts, and secret scanning with push protection if your plan includes it.
- [ ] Actions: allow only GitHub-authored and selected actions; set workflow permissions to read-only by default.
- [ ] Create `staging` and `production` environments; require a reviewer for `production` deployments.

### 7. Sentry

- [ ] **Before creating anything,** check which regions Sentry can store your organisation's data in. If none is
      in India, using it sends error data outside India and needs an explicit decision (golden rule 12). The options
      are to self-host Sentry in `ap-south-1`, or to get approval and turn on server-side scrubbing so no
      transcript text, names or contact details are sent.
- [ ] Once decided: create one project for the API and workers and one for the web app, with separate environments
      for staging and production. Put each DSN in the secret store as `SENTRY_DSN`.
- [ ] Turn on default PII scrubbing and IP address scrubbing.

### 8. Not in this checklist

- **Langfuse:** self-host in `ap-south-1` unless a hosted region is approved (same rule as Sentry). Covered when
  plan task 5.1 builds the LLM gateway.
- **LLM providers:** decided through `docs/llm-providers.md` (plan task 0.6).
- **Amazon SES:** verify the sending domain in `ap-south-1` (with DKIM) and request production access before
  notifications ship (plan task 2.7).
- **Identity provider (OIDC):** Auth0 or Keycloak, decided in ADR 0002 (plan task 1.5).

### 9. Check it works

- [ ] Fill in the environment's settings (see `.env.example`) from the secret store.
- [ ] Run `uv run python scripts/check_env.py` on a machine in that environment. Every service should print PASS.

<a id="part-7"></a>

# Part 7. Quality and evaluation

<a id="doc-docs-annotation-guidelines-md"></a>

## Annotation guidelines: gold transcripts

*Source: [`docs/annotation-guidelines.md`](annotation-guidelines.md)*

For people who label recordings in Label Studio (setup: `infra/annotation/README.md`).

Your transcripts become the **gold set**: the reference we compare Sabha's automatic transcripts and
speaker labels against. A mistake in the gold set turns into a wrong score for the system, so we
prefer slow and exact over fast. When a rule below doesn't cover what you hear, ask the annotation lead
and note the task number, rather than guessing.

### Before you start

- **The recordings are real.** They contain real teachers, front-desk staff, parents and students.
  Listen with headphones in a private place. Work only inside Label Studio: don't download recordings,
  don't copy transcript text out, and never paste it into another website or app (translation or
  transliteration sites, chatbots, online keyboards). Text pasted there leaves our control.
- **Typing Devanagari.** Use the Hindi phonetic or transliteration keyboard built into Windows or
  macOS, which works offline. Don't use websites or browser extensions to type Hindi. If you can't type
  Devanagari, take only recordings marked `english` (shown above the waveform as the language mix).
- **Stop if a recording shouldn't be there.** If you hear something that doesn't look like a lesson or
  a front-desk conversation (a counselling session, a private phone call, a medical conversation), stop
  and tell the lead. Don't annotate it.

### How a task works

1. Press a label key (`1` Teacher, `2` Student(s), `3` Receptionist, `4` Caller, `5` Other,
   `6` Silence) or click the label.
2. Drag across the waveform over one speaker's turn. That makes a region.
3. Click the region and type what was said in the box. Leave the box empty only for Silence.
4. Repeat until every part of the recording where someone speaks is covered, then **Submit**.

The short version of these rules is shown above the waveform in every task.

### 1. Regions

- One region is one speaker's turn. When the speaker changes, start a new region.
- Split a turn longer than about 30 seconds at a natural pause. Short regions are easier to check.
- Start the region just before the first sound of the first word and end it just after the last word.
  Zoom in on the waveform to place the edges. Never cut through a word.
- Small gaps between regions are fine. Regions of different speakers may overlap (section 8).
- Every stretch of speech that belongs to the conversation must be inside a region.

### 2. Speaker labels

Labels describe the person's **role in this recording**, not who they are. Never try to work out or note
which student is speaking.

| Label | Use for |
| --- | --- |
| Teacher | The staff member leading the lesson. One person per recording. A second adult in the room (another teacher, the principal on a visit, an assistant) is **Other**. |
| Student(s) | Any student or group of students: one child, several, or the whole class together. |
| Receptionist | The front-desk staff member handling the call or visit. |
| Caller | The person the receptionist is serving, on the phone or at the desk: a parent, visitor, supplier, job applicant. Also a student or teacher if they are the one being served. |
| Other | Anyone else who speaks in the conversation: another staff member, a parent who walks into a class, a school announcement, the recorded "this call may be recorded" notice, hold messages and other automated voices. |
| Silence | Nobody in the conversation is speaking for 2 seconds or more (section 9). |

Teaching recordings normally use Teacher, Student(s), Other and Silence. Reception recordings normally
use Receptionist, Caller, Other and Silence. If you truly can't tell who is speaking, use **Other**.

### 3. Write exactly what was said

- Write every word in the order it was said. Don't correct grammar, finish sentences, summarise or
  translate.
- Keep repetitions and false starts: `the the answer is`, `we will we are going to`.
- A word cut off halfway: write the part you heard and a hyphen: `photosyn-`. The hyphen is used only
  for this.
- Write the word the speaker meant in its normal spelling, not a spelling of their accent: if someone
  says "vater" for water, write `water`. If they said a different word, write that word.
- Contractions as said: `don't`, `I'm`, `gonna` if they said "gonna".
- Punctuation and capital letters are optional and are not checked. Use only `.` `,` `?` (or `।`)
  if you want them. Never use quotation marks, and never use square brackets except for the tokens in
  sections 6 and 7.
- English spelling: Indian/British (`colour`, `centre`). Hindi spelling: the normal dictionary
  spelling. Don't spend time on fine points such as nukta (ज़ or ज) or chandrabindu (ँ or ं): write it
  the way you normally would, and the same way every time.
- Write only speech. No descriptions or notes in the text (no "laughs", no "the boy at the back").

#### Fillers

Always write fillers. Use these spellings so everyone writes them the same way:

| You hear | Type |
| --- | --- |
| um, umm, ummm | `umm` |
| uh, er | `uh` |
| hmm, mm, mm-hmm | `hmm` |
| haan, haa | `हाँ` |
| accha, achha | `अच्छा` |
| matlab | `मतलब` |
| arre | `अरे` |
| na, naa (at the end of a sentence) | `ना` |
| ji | `जी` |
| ok, okay | `okay` |

### 4. Hindi, English and Hinglish: which script

**The script follows the language of each word.**

- Hindi words in **Devanagari**. English words in **Roman** (English letters). Mix them inside one
  sentence exactly as the speaker did:
  - Right: `आज हम photosynthesis पढ़ेंगे`
  - Wrong: `aaj hum photosynthesis padhenge` (Hindi in Roman)
  - Wrong: `आज हम फोटोसिंथेसिस पढ़ेंगे` (English in Devanagari)
- English words used every day in Hindi speech are still English: `class`, `homework`, `fees`,
  `admission`, `test`, `copy`, `sir`, `ma'am`, `bus`, `sorry`, `please`, `thank you`, `okay`.
- Hindi grammar around an English word stays Devanagari: `copies में लिखो`, `homework करो`.
- Hindi words inside English speech stay Devanagari: `very good, शाबाश`.
- **Proper names** of people, places, schools, books and organisations are always in Roman, as they
  would be written in English: `Pooja`, `Jaipur`, `Sunrise Public School`, `NCERT`. (Most personal
  names are replaced by tokens anyway, section 6.)
- Abbreviations said letter by letter are written in capitals: `NCERT`, `PTM`, `CBSE`, `UPI`.
- Words from Rajasthani or another language written in Devanagari: Devanagari. A whole turn in a
  language you can't write: label the speaker, write `[inaudible]`, and tell the lead.
- A word that could belong to either language: use the language of the words around it.

### 5. Numbers

- Write numbers **as words, exactly as spoken, in the language spoken**. Never digits.
  - `twenty five`, `पच्चीस`, `class ten`, `page number पच्चीस`, `two thousand twenty six`,
    `ten thirty`, `five hundred rupees`, `पाँच सौ रुपये`, `one by two`, `x square plus two x`.
- No hyphens in numbers: `twenty five`, not `twenty-five`.
- Numbers said digit by digit are written digit by digit: `four five two`.
- Private numbers (phone, Aadhaar, admission number and similar) are replaced by a token, section 6.

### 6. Private details: tokens

Replace private details with these exact tokens: lowercase, in square brackets, nothing else inside.
One token replaces the whole name or number. Keep words around it, such as honorifics: `[name] जी`,
`[student] की mother`, `[student]'s copy`.

| Token | Replaces |
| --- | --- |
| `[student]` | Any student's name or nickname, first name or surname, whoever says it. |
| `[name]` | The name of any private person who is not school staff: parents, callers, visitors, relatives, other children. |
| `[phone]` | Phone numbers. |
| `[id]` | Aadhaar, PAN, admission, roll, registration, receipt and bank account numbers, and similar. |
| `[email]` | Email addresses. |
| `[address]` | Home addresses: house or flat number, street, locality. |

- **Never write a student's name.** If you are not sure whether a name belongs to a student, use
  `[student]`.
- **Staff names are kept** as spoken: teachers, front-desk staff, the principal, other staff
  (`Sharma ma'am`, `Pooja`). Feedback is about staff, so their names are part of the conversation. If
  you are not sure whether someone is staff, use `[name]`.
- Class and section (`class eight B`), subjects, and the school's name are not private: keep them.

### 7. Unclear speech: `[inaudible]`

- If you can't make out a word, listen again up to two more times, slowed down. If you still can't
  make it out, write `[inaudible]`. One `[inaudible]` covers one word or several in a row.
- Don't guess. If you are fairly sure of a word, write it.
- A whole region you can't make out: give it the right speaker label and the text `[inaudible]`.
- `[inaudible]` is the only marker for unclear speech. Don't use `???`, `(unclear)` or similar.

### 8. Overlapping speech

- When two people speak at once, give each person their own region. The regions overlap in time, and
  each region contains only that person's words.
- The whole class answering together is one Student(s) region. Write what the group said if it is clear
  (`yes ma'am`), otherwise `[inaudible]`.
- Short reactions during someone else's turn (`हाँ`, `hmm`, `okay`) get their own region when you can
  hear them clearly as words. Ignore murmur you can't make out.
- Voices that are not part of the conversation (a corridor, the next classroom, a TV) are not
  transcribed.

### 9. Silence

- Mark **Silence** for any stretch of **2 seconds or more** in which nobody in the conversation speaks:
  students writing, waiting for an answer, a caller on hold. Leave its text empty.
- Shorter pauses need no region.
- Sounds without speech (bell, fan, traffic, hold music) and background chatter that isn't part of the
  conversation count as silence.
- Silence regions should not overlap speech regions.

### 10. Before you submit

- Play the recording through once more and check every region: right label, right edges, and text for
  every region except Silence.
- Then **Submit**. To correct a task later, open your existing annotation, fix it and click **Update**.
  Don't create a second annotation.
- Exported tasks are checked automatically. A task comes back to you if a speech region has no text, a
  Silence region has text, or a region has no label.

### Worked examples

All names, schools and numbers in these examples are made up. Times are minutes:seconds.

#### Example 1: Hinglish lesson, a student is named, speakers overlap

What you hear: the teacher says "Accha, so aaj hum photosynthesis padhenge. Umm, kaun batayega plants
khaana kaise banate hain?" A boy answers "Sunlight se, ma'am." Before he finishes, the teacher says
"Haan, bilkul. Aarav, tum batao chlorophyll kya karta hai?"

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.5 | 0:06.0 | Teacher | `अच्छा, so आज हम photosynthesis पढ़ेंगे. umm, कौन बताएगा plants खाना कैसे बनाते हैं?` |
| 0:06.8 | 0:08.3 | Student(s) | `sunlight से ma'am` |
| 0:08.0 | 0:12.3 | Teacher | `हाँ, बिल्कुल. [student], तुम बताओ chlorophyll क्या करता है?` |

Why: Hindi words in Devanagari, English words in Roman; fillers spelled as in the table; the student's
name becomes `[student]`; the overlapping turns are separate regions.

#### Example 2: English lesson, quiet writing time, the class answers together

What you hear: "Write the answer in your copies. You have one minute." About nine seconds of pens on
paper. "Done? Okay, so what is the answer?" The class together: "Twenty five, ma'am!" Then one student
at the back mumbles something you can't catch, followed by "I got twenty four."

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:04.1 | Teacher | `write the answer in your copies. you have one minute` |
| 0:04.1 | 0:13.0 | Silence | (empty) |
| 0:13.0 | 0:16.2 | Teacher | `done? okay, so what is the answer?` |
| 0:16.4 | 0:18.0 | Student(s) | `twenty five ma'am` |
| 0:18.3 | 0:21.0 | Student(s) | `[inaudible] I got twenty four` |

Why: numbers in words; the whole class is one Student(s) region; the pause of 2 seconds or more is
Silence with empty text; the unclear words are `[inaudible]`, not a guess.

#### Example 3: Reception phone call in Hinglish with private details

What you hear: a recorded voice: "This call may be recorded for training and quality purposes." The
receptionist: "Good morning, Sunrise Public School, Pooja bol rahi hoon." The caller: "Haan ji, main
Rakesh Verma bol raha hoon, meri beti Ananya ke admission ke baare mein." The receptionist: "Ji sir,
aapka number bata dijiye, main callback karwa deti hoon." The caller reads out a mobile number.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:03.5 | Other | `this call may be recorded for training and quality purposes` |
| 0:03.6 | 0:06.2 | Receptionist | `good morning, Sunrise Public School, Pooja बोल रही हूँ` |
| 0:06.4 | 0:11.0 | Caller | `हाँ जी, मैं [name] बोल रहा हूँ, मेरी बेटी [student] के admission के बारे में` |
| 0:11.2 | 0:14.5 | Receptionist | `जी sir, आपका number बता दीजिए, मैं callback करवा देती हूँ` |
| 0:14.7 | 0:19.0 | Caller | `[phone]` |

Why: the recorded notice is Other; the receptionist's own name is kept (staff) and written in Roman
(proper name); the caller's name is `[name]` and his daughter's is `[student]`; the phone number is one
`[phone]` token.

#### Example 4: Walk-in enquiry at the front desk, a colleague interrupts

What you hear: a parent at the desk: "Hello, I wanted to ask about the fee for class three." The
receptionist: "Sure. For class three it's twelve thousand five hundred per quarter." A colleague
walks up: "Pooja, principal sir wants the visitor register." The receptionist, to the colleague: "One
minute, sir." Then to the parent: "Sorry, umm, you were saying?" The parent starts asking "Can I pay by
UPI?" while the receptionist is still finishing her sentence.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:03.0 | Caller | `hello, I wanted to ask about the fee for class three` |
| 0:03.2 | 0:07.4 | Receptionist | `sure. for class three it's twelve thousand five hundred per quarter` |
| 0:07.9 | 0:10.6 | Other | `Pooja, principal sir wants the visitor register` |
| 0:10.8 | 0:11.7 | Receptionist | `one minute, sir` |
| 0:12.0 | 0:14.2 | Receptionist | `sorry, umm, you were saying?` |
| 0:13.8 | 0:15.6 | Caller | `can I pay by UPI?` |

Why: the colleague is Other even though he is staff, because he is not the receptionist being recorded
or the person being served; amounts in words; `UPI` in capitals because it is said letter by letter;
the overlapping question is its own region.

#### Example 5: Hindi lesson with an announcement, students named, a bell

What you hear: the speaker system: "Attention please, all class ten students report to the hall after
the break." The teacher: "Chalo, sab dhyaan do. Riya, kitaab band karo." A girl: "Ma'am, Mohit ne mera
pen le liya." The teacher: "Mohit, pen wapas karo." Then the bell rings and nobody speaks for about
four seconds.

| Start | End | Label | Text |
| --- | --- | --- | --- |
| 0:00.0 | 0:05.2 | Other | `attention please, all class ten students report to the hall after the break` |
| 0:05.8 | 0:09.0 | Teacher | `चलो, सब ध्यान दो. [student], किताब बंद करो` |
| 0:09.4 | 0:12.0 | Student(s) | `ma'am, [student] ने मेरा pen ले लिया` |
| 0:12.2 | 0:14.0 | Teacher | `[student], pen वापस करो` |
| 0:14.0 | 0:18.1 | Silence | (empty) |

Why: the announcement is Other; every student's name is `[student]`, whoever says it; `ma'am` and
`pen` are English words in Roman; the bell with no speech is Silence.

<a id="doc-docs-raters-guide-md"></a>

## Rater guide: scoring lessons with the teaching rubric

*Source: [`docs/raters/guide.md`](raters/guide.md)*

For the people who score lessons by hand (plan task P4.4). Your scores are the reference the software is checked
against, so they matter more than speed.

### The ground rules

- **Score the teacher's teaching, never the students.** Students' answers are only evidence of what the teacher
  did. Never write a student's name in a note.
- **Score blind.** Your sheet has no AI scores, and you must not look for them. Don't discuss scores with other
  raters until the coordinator says the round is closed.
- **Score what you can point to.** Every anchor below describes something you can hear or read. If you can't point
  to a moment for a score, choose the lower level.
- **Use the whole lesson.** Listen to, or read, the full recording before scoring any dimension.
- **One score per dimension, a whole number from 1 to 5.** The sheet rejects blanks, halves and anything outside
  1 to 5.

### How to fill in your sheet

1. Open your sheet (`scores-<your rater id>.csv`, imported into Google Sheets) and the **anchors** tab next to it.
2. Each row is one recording and one dimension, in a shuffled order. Open the transcript link in the row.
3. Read the dimension's anchors, find the level that matches what you saw, and type the number in `score`.
4. In `note`, write the time of the moment that decided your score, for example `12:40 asks "kyun?" and waits`.
   One short line is enough.
5. When every row has a score, download the sheet as CSV and send it to the coordinator. The import script checks
   it; if anything is missing or out of range, the whole sheet comes back to you with the list of problems.

### Choosing between two levels

- Start from level 3 and ask: does the lesson clearly show everything in level 4? If yes, check level 5. If no,
  check whether it falls short of level 3.
- If a lesson shows level 5 behaviour once and level 2 behaviour the rest of the time, score what was typical,
  and mention the strong moment in the note.
- Can't decide between two levels after reading both anchors twice? Choose the lower one and say why in the note.

### Worked examples

These use the example lines written into the rubric file, so they show the two ends of each scale.

**1. Checks for understanding.** The teacher says: *"Sab samajh aa gaya na? Good. Chalo next topic."* and nothing
else checks understanding in the lesson. That is a yes/no check accepted without anyone explaining anything. It
matches level 1 ("asks 'samajh aaya?' and moves on without waiting for a reply"). **Score: 1.** Note: the time of
the line.

Compare: *"Ek kaam karo, copy mein 2/5 + 1/5 solve karke dikhao. ... Kuch logon ne 3/10 likha hai. Ruko, ek baar
phir dekhte hain denominator ke saath kya hota hai."* Students apply the idea, the teacher looks at the answers and
re-explains because of them. If the teacher does this at several points with more than one student, that is level
5. If it happens once, level 4 fits better: "responds to wrong answers by correcting or re-explaining".

**2. Use of examples.** *"Fractions add karne ka rule board pe likh diya hai, bas yaad kar lo, exam mein aayega."*
No example, no worked problem: level 1. Against that, *"Socho ek pizza ke 8 slices hain aur Aman ne 3 kha liye, toh
usne pizza ka 3/8 khaaya. Ab yahi 3/8 number line pe dikhaate hain, dekho same cheez hai."* is an everyday example
linked back to the concept. Level 5 also asks for two or more examples and one worked step by step, so check the
rest of the lesson before giving 5.

**3. Recap and closure.** *"Bell baj gayi, chalo bas, kal milte hain."* The lesson ends with no summary: level 1.
If the recording stops before the end of the lesson, don't guess: write `recording ends early` in the note and tell
the coordinator, because the rubric does not yet say how to score that case.

### The anchors (teaching rubric v0.1)

Generated from `rubrics/teaching.school.v0.1.yaml`. The anchors tab in your sheet comes from the same file; if the
two ever differ, the sheet is right and this guide needs regenerating.

#### Concept clarity (`concept_clarity`)

The teacher states the main idea of the lesson, defines its key terms and explains it in a logical order of steps.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher never states the main idea, and the explanation contradicts itself or contains a clear factual error that is not corrected. |
| 2 | The teacher names the topic but uses key terms without defining them, and the explanation skips steps or jumps back and forth. |
| 3 | The teacher states the main idea and defines most key terms, but at least one step is skipped or explained out of order. |
| 4 | The teacher states the main idea, defines each key term when first used, and explains it step by step in order. |
| 5 | The teacher states the main idea at the start, defines each key term when first used, explains it step by step, and re-explains it in a different way (simpler words, the other language or a board diagram) when a student asks a question or gives a wrong answer. |

#### Use of examples (`use_of_examples`)

The teacher uses examples, analogies, demonstrations or worked problems that match the concept being taught and links them back to it.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher gives no example, analogy, demonstration or worked problem at any point in the explanation. |
| 2 | The teacher mentions an example only in passing or gives one that does not match the concept being taught. |
| 3 | The teacher gives at least one relevant example or worked problem but does not say how it connects to the concept. |
| 4 | The teacher gives two or more relevant examples or worked problems and says how each connects to the concept. |
| 5 | The teacher gives two or more relevant examples, including one from an everyday setting such as home, the market or sports, works at least one through step by step, and links each back to the concept. |

#### Checks for understanding (`checks_for_understanding`)

The teacher checks at points during the lesson whether students can explain or use the idea, and acts on what the answers show.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher does not check understanding at any point, or asks 'samajh aaya?' and moves on without waiting for a reply. |
| 2 | The teacher asks only yes/no checks such as 'clear hai?' and accepts a chorus 'yes' without asking anyone to explain or show working. |
| 3 | The teacher asks at least one check that needs students to explain, answer or show working, but moves on without responding to wrong or missing answers. |
| 4 | The teacher asks checks that need an answer or explanation at more than one point in the lesson and responds to wrong answers by correcting or re-explaining. |
| 5 | The teacher checks at several points with tasks that need students to explain or apply the idea, invites answers from more than one student, and re-explains or changes the next step based on the answers given. |

#### Questioning quality (`questioning_quality`)

The teacher asks a mix of questions, including open questions that ask students to explain, compare or predict, gives time to answer and follows up on answers.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher asks no questions, or answers their own questions straight away without pausing for students. |
| 2 | The teacher asks only recall questions with one-word answers and moves on after the first answer. |
| 3 | The teacher asks mostly recall questions with at least one open question (why, how, what if), but answers it themselves or takes the first reply without a pause. |
| 4 | The teacher asks several open questions, pauses for answers, and follows up on some answers with prompts such as 'kyun?' or 'kaise pata?'. |
| 5 | The teacher regularly asks open questions, pauses before taking answers, and follows up by asking for reasons or by asking another student to agree, disagree or build on an answer. |

#### Pacing (`pacing`)

The teacher moves through the parts of the lesson at a speed that leaves time for explanation, questions and practice, and changes speed in response to student questions or answers.

| Score | What you can point to |
| --- | --- |
| 1 | The teacher talks through the material without pausing for questions or practice, or leaves long stretches with no instruction, and rushes or skips content at the end ('baaki ghar pe padh lena'). |
| 2 | The teacher spends most of the lesson on one part and rushes through the rest, with few pauses for questions or practice. |
| 3 | The teacher gives time to each part of the lesson with some pauses for questions, but keeps the same speed after student questions or wrong answers. |
| 4 | The teacher gives time to each part of the lesson, including practice, pauses for questions, and slows down at least once to re-explain after a student question or wrong answer. |
| 5 | The teacher announces the move from one part of the lesson to the next, pauses for questions and practice in each part, slows down to re-explain after wrong answers, and moves on once students answer correctly. |

#### Recap and closure (`recap_and_closure`)

The teacher ends the lesson by restating the key points, connecting them to the lesson's aim and saying what comes next.

| Score | What you can point to |
| --- | --- |
| 1 | The lesson ends without any summary, for example stopping mid-explanation at the bell or ending with only 'chalo, bas'. |
| 2 | The teacher ends with only a homework instruction or 'revise kar lena' without restating any key point. |
| 3 | The teacher lists what was covered ('aaj humne X aur Y kiya') but does not restate the key points themselves. |
| 4 | The teacher restates the key points of the lesson at the end and says what comes next or what the homework practises. |
| 5 | The teacher asks students to state the key points, adds or corrects what is missing, connects them to the lesson's aim, and says what comes next or what the homework practises. |

<a id="doc-docs-rubrics-review-sheet-md"></a>

## Rubric review sheets (draft v0.1)

*Source: [`docs/rubrics/review-sheet.md`](rubrics/review-sheet.md)*

**DRAFT v0.1 — for review with an academic head**

Sabha school pilot rubrics: teaching and reception. Sources: `rubrics/teaching.school.v0.1.yaml` and
`rubrics/reception.school.v0.1.yaml`. Nothing here is final. Weights and anchors are proposals.

**How to mark up:** in the Notes column, write keep, change or drop, a better wording, or a different
weight. Scores run from 1 (lowest) to 5 (highest). Anchors describe only what the staff member says or
does that a rater can point to in the recording. Students and callers are never scored. All names and
details in the examples are fictional. Print in landscape.

Reviewer: ____________________  Date: ____________________

### Teaching rubric (`teaching.school.v0.1`)

Roles: teacher (the person analysed), students (context only). Weights total 1.00.

| Dimension | Weight | Definition | 1 | 3 | 5 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Concept clarity<br>`concept_clarity` | 0.25 | The teacher states the main idea of the lesson, defines its key terms and explains it in a logical order of steps. | The teacher never states the main idea, and the explanation contradicts itself or contains a clear factual error that is not corrected. | The teacher states the main idea and defines most key terms, but at least one step is skipped or explained out of order. | The teacher states the main idea at the start, defines each key term when first used, explains it step by step, and re-explains it in a different way (simpler words, the other language or a board diagram) when a student asks a question or gives a wrong answer. | |
| Use of examples<br>`use_of_examples` | 0.15 | The teacher uses examples, analogies, demonstrations or worked problems that match the concept being taught and links them back to it. | The teacher gives no example, analogy, demonstration or worked problem at any point in the explanation. | The teacher gives at least one relevant example or worked problem but does not say how it connects to the concept. | The teacher gives two or more relevant examples, including one from an everyday setting such as home, the market or sports, works at least one through step by step, and links each back to the concept. | |
| Checks for understanding<br>`checks_for_understanding` | 0.20 | The teacher checks at points during the lesson whether students can explain or use the idea, and acts on what the answers show. | The teacher does not check understanding at any point, or asks 'samajh aaya?' and moves on without waiting for a reply. | The teacher asks at least one check that needs students to explain, answer or show working, but moves on without responding to wrong or missing answers. | The teacher checks at several points with tasks that need students to explain or apply the idea, invites answers from more than one student, and re-explains or changes the next step based on the answers given. | |
| Questioning quality<br>`questioning_quality` | 0.15 | The teacher asks a mix of questions, including open questions that ask students to explain, compare or predict, gives time to answer and follows up on answers. | The teacher asks no questions, or answers their own questions straight away without pausing for students. | The teacher asks mostly recall questions with at least one open question (why, how, what if), but answers it themselves or takes the first reply without a pause. | The teacher regularly asks open questions, pauses before taking answers, and follows up by asking for reasons or by asking another student to agree, disagree or build on an answer. | |
| Pacing<br>`pacing` | 0.10 | The teacher moves through the parts of the lesson at a speed that leaves time for explanation, questions and practice, and changes speed in response to student questions or answers. | The teacher talks through the material without pausing for questions or practice, or leaves long stretches with no instruction, and rushes or skips content at the end ('baaki ghar pe padh lena'). | The teacher gives time to each part of the lesson with some pauses for questions, but keeps the same speed after student questions or wrong answers. | The teacher announces the move from one part of the lesson to the next, pauses for questions and practice in each part, slows down to re-explain after wrong answers, and moves on once students answer correctly. | |
| Recap and closure<br>`recap_and_closure` | 0.15 | The teacher ends the lesson by restating the key points, connecting them to the lesson's aim and saying what comes next. | The lesson ends without any summary, for example stopping mid-explanation at the bell or ending with only 'chalo, bas'. | The teacher lists what was covered ('aaj humne X aur Y kiya') but does not restate the key points themselves. | The teacher asks students to state the key points, adds or corrects what is missing, connects them to the lesson's aim, and says what comes next or what the homework practises. | |

**Anchors 2 and 4**

| Dimension | 2 | 4 | Notes |
| --- | --- | --- | --- |
| Concept clarity | The teacher names the topic but uses key terms without defining them, and the explanation skips steps or jumps back and forth. | The teacher states the main idea, defines each key term when first used, and explains it step by step in order. | |
| Use of examples | The teacher mentions an example only in passing or gives one that does not match the concept being taught. | The teacher gives two or more relevant examples or worked problems and says how each connects to the concept. | |
| Checks for understanding | The teacher asks only yes/no checks such as 'clear hai?' and accepts a chorus 'yes' without asking anyone to explain or show working. | The teacher asks checks that need an answer or explanation at more than one point in the lesson and responds to wrong answers by correcting or re-explaining. | |
| Questioning quality | The teacher asks only recall questions with one-word answers and moves on after the first answer. | The teacher asks several open questions, pauses for answers, and follows up on some answers with prompts such as 'kyun?' or 'kaise pata?'. | |
| Pacing | The teacher spends most of the lesson on one part and rushes through the rest, with few pauses for questions or practice. | The teacher gives time to each part of the lesson, including practice, pauses for questions, and slows down at least once to re-explain after a student question or wrong answer. | |
| Recap and closure | The teacher ends with only a homework instruction or 'revise kar lena' without restating any key point. | The teacher restates the key points of the lesson at the end and says what comes next or what the homework practises. | |

**Hinglish examples (do they sound like your teachers?)**

| Dimension | Example at level 1 | Example at level 5 | Notes |
| --- | --- | --- | --- |
| Concept clarity | "Toh photosynthesis mein plant oxygen leta hai aur CO2 chhodta hai... haan, respiration bhi yahi hai, same cheez. Chalo next." (contains a deliberate error) | "Aaj ka main idea: photosynthesis matlab plant sunlight, paani aur CO2 se apna khana banata hai. 'Chlorophyll' yaani leaf ka green pigment, jo sunlight absorb karta hai. Pehle yeh samjho, phir steps dekhenge." | |
| Use of examples | "Fractions add karne ka rule board pe likh diya hai, bas yaad kar lo, exam mein aayega." | "Socho ek pizza ke 8 slices hain aur Aman ne 3 kha liye, toh usne pizza ka 3/8 khaaya. Ab yahi 3/8 number line pe dikhaate hain, dekho same cheez hai." | |
| Checks for understanding | "Sab samajh aa gaya na? Good. Chalo next topic." | "Ek kaam karo, copy mein 2/5 + 1/5 solve karke dikhao. ... Kuch logon ne 3/10 likha hai. Ruko, ek baar phir dekhte hain denominator ke saath kya hota hai." | |
| Questioning quality | "Plants ko khana banane ke liye kya chahiye? Sunlight. Theek hai, aage badhte hain." | "Agar ek plant ko ek hafta andhere mein rakh dein toh kya hoga, aur kyun? ... Sana keh rahi hai leaves peeli ho jaayengi. Kaun agree karta hai, kaun nahi? Reason ke saath batao." | |
| Pacing | "Time kam hai bachcho, baaki chapter fatafat khatam karte hain, jo samajh na aaye ghar pe padh lena." | "Is sawaal pe kaafi answers galat aaye, toh thoda ruk ke ek baar phir karte hain. Phir paanch minute practice, uske baad next topic." | |
| Recap and closure | "Bell baj gayi, chalo bas, kal milte hain." | "Bell se pehle, Ritu, aaj ke do main points batao? ... Haan, aur ek cheez add karo: denominator same ho tabhi seedha add karte hain. Kal unlike fractions karenge, isliye homework mein page 42 ke pehle paanch sawaal." | |

**Quotes required per score:** 2 for concept clarity, checks for understanding and questioning quality; 1 for the rest.
**Shown next to the scores (counted by software, not judged, no targets set):** teacher talk share, teacher question count,
open question ratio, words per minute, silence share, longest silence, longest monologue.
**Report sections:** summary, strengths, gaps, suggestions.
**Visibility:** scores stay hidden until agreement with human raters (Cohen's kappa) is at least 0.60. Not yet measured.

<div style="page-break-after: always"></div>

### Reception rubric (`reception.school.v0.1`) — DRAFT v0.1

Roles: receptionist (the person analysed), caller (context only). Weights total 1.00.
"[school name]" in the examples stands in for your school's name.

| Dimension | Weight | Definition | 1 | 3 | 5 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Intent captured<br>`intent_captured` | 0.20 | The receptionist finds out and confirms the caller's reason for calling before giving information or taking action. | The receptionist does not ask why the person is calling and answers a different question from the one the caller asked. | The receptionist asks at least one follow-up question about the request (for example the child's class or which fee) but does not repeat the request back to the caller. | The receptionist asks follow-up questions for all needed details, repeats the full request back in their own words, and asks whether the caller has any other request before closing. | |
| Information accuracy\*<br>`information_accuracy` | 0.25 | The receptionist gives specific, consistent information and says so when a detail needs to be confirmed rather than guessing. | The receptionist gives information that contradicts itself within the call (for example two different fee amounts) or guesses with words like 'shayad' or 'lagta hai' without offering to confirm. | The receptionist gives specific details for the main request but is vague on at least one follow-up detail and does not say whether it will be confirmed. | The receptionist gives specific, consistent details, names the source (fee chart, circular or website page) where relevant, offers to confirm any open detail with a named role and a time, and repeats the key figures back at the end. | |
| Courtesy<br>`courtesy` | 0.15 | The receptionist uses polite, respectful language from greeting to close and lets the caller finish speaking. | The receptionist uses dismissive or rude language (for example 'pata nahi' and hanging up), interrupts repeatedly, or skips both greeting and closing. | The receptionist greets and closes politely but gives curt replies or interrupts the caller at least once during the call. | The receptionist greets with the school name and their own name, uses polite forms throughout, lets the caller finish speaking, acknowledges any concern or complaint in words before answering, and thanks the caller at the close. | |
| Resolution<br>`resolution` | 0.25 | The receptionist ends the call with the caller's request answered or with a specific next step that says who will act and by when. | The call ends with the caller's request neither answered nor given any next step. | The receptionist answers the request or gives a next step, but leaves out who will act or by when. | The receptionist answers the request or gives a next step naming who will act and by when, summarises it back to the caller, and confirms how the caller will be contacted if a call-back is promised. | |
| Escalation handling†<br>`escalation_handling` | 0.15 | When a request is a complaint, is urgent or is outside the receptionist's authority, the receptionist passes it to the right role or team in a way the caller can follow up on. | The receptionist argues with or dismisses a complaint or out-of-scope request, or transfers or ends the call without saying where the request is going. | The receptionist names the role or team that will handle the request but does not note the details or say when the caller will hear back. | The receptionist acknowledges the issue in words, names the role or team, repeats the key details that will be passed on, tells the caller when and how they will hear back, and gives a way to follow up if they do not. | |

\* Raters may not know the school's facts. The school needs to supply a fact sheet (fees, timings, dates, routes,
contacts) for raters. Until then this is judged only on what is heard: specific or vague, consistent or
contradictory, confirming or guessing.
† Many calls need no escalation. How should those calls be scored? (See questions.)

**Anchors 2 and 4**

| Dimension | 2 | 4 | Notes |
| --- | --- | --- | --- |
| Intent captured | The receptionist responds to the first thing the caller says without asking any follow-up question about the request. | The receptionist asks follow-up questions to get the needed details and repeats the main request back to the caller before answering. | |
| Information accuracy | The receptionist gives some specific details but leaves key details vague ('thoda zyada hai', 'aas paas') and does not offer to confirm them. | The receptionist gives specific details (amounts, dates, timings, document names) that stay consistent through the call, and says they will confirm any detail they cannot give on the spot. | |
| Courtesy | The receptionist greets the caller but gives curt replies, interrupts the caller more than once, or ends the call without a closing. | The receptionist greets with the school name, uses polite forms ('ji', 'aap', 'please') throughout, lets the caller finish speaking, and closes politely. | |
| Resolution | The receptionist gives a vague next step such as 'dekhte hain' or 'baad mein call karna' with no person, action or time named. | The receptionist answers the request or gives a next step that names who will act and by when. | |
| Escalation handling | The receptionist says someone else will handle it but does not name the person, role or team, or how the caller will hear back. | The receptionist names the role or team, notes the key details of the issue, and tells the caller when they will hear back. | |

**Hinglish examples (do they sound like your front desk?)**

| Dimension | Example at level 1 | Example at level 5 | Notes |
| --- | --- | --- | --- |
| Intent captured | "Haan ji, admission ke liye hi call kiya hoga, form office se le jaiye." | "Toh aap jaanna chahte hain ki Class 3 ke liye bus Sector 12 se jaati hai ya nahi, aur uski monthly fee kitni hai. Sahi samjha maine? Aur koi cheez?" | |
| Information accuracy | "Fees? Shayad 40-45 hazaar hogi... ya 50, pakka nahi pata, aap aa ke dekh lo." | "Class 5 ki tuition fee 38,000 rupaye per year hai, do instalments mein, yeh current fee chart se bata rahi hoon. Transport fee route pe depend karti hai, woh main accounts se confirm karke aaj shaam 5 baje tak call karti hoon." | |
| Courtesy | "Haan bolo. ... Arre yeh sab office time mein aake poochho, abhi busy hoon." | "Good morning, [school name], main Neha bol rahi hoon. Bataiye ji, main aapki kya help kar sakti hoon?" | |
| Resolution | "Pata nahi madam, aap kabhi aake dekh lena. ... Haan theek hai, bye." | "Toh final: aapki transport request maine note kar li hai, transport incharge kal 12 baje tak aapko isi number pe call karenge. Tab tak call na aaye toh 1 baje ke baad mujhe direct call kar lijiye." | |
| Escalation handling | "Complaint hai toh principal se baat karo, mere paas kuch nahi hai. ... Nahi, number nahi de sakti." | "Bus roz late aa rahi hai, yeh sach mein pareshani ki baat hai. Main yeh complaint abhi transport incharge ko bhej rahi hoon, route number aur dates note kar li hain. Woh aaj 4 baje tak aapko call karenge, na aaye toh mujhe is reference number ke saath call kijiye." | |

**Quotes required per score:** 2 for information accuracy and courtesy; 1 for the rest.
**Shown next to the scores (counted by software, not judged, no targets set):** call duration, receptionist talk share,
caller talk share, silence share, longest silence (such as a hold), number of long gaps or holds.
**Report sections:** summary, strengths, gaps, suggestions, category, status, follow-up (what happens next and which role owns it).
**Draft category values:** admission enquiry, fee query, transport, general information (timings, holidays, events, documents), complaint, other.
**Draft status values:** resolved, follow-up needed, escalated.
**Visibility:** scores stay hidden until agreement with human raters (Cohen's kappa) is at least 0.60. Not yet measured.

<div style="page-break-after: always"></div>

### Questions for the reviewer — DRAFT v0.1

1. **Weights.** Are the weights right for your school? Should any dimension count more or less?
2. **Observable anchors.** Could two raters listening to the same recording point to the same moment for each
   anchor? Circle any anchor that needs guesswork.
3. **Steps between levels.** Is the step from each level to the next clear, especially between 2, 3 and 4?
4. **Hinglish examples.** Do the examples sound like your teachers and front-desk staff actually speak? Please
   rewrite any that sound off.
5. **Missing or extra dimensions.** Is anything important missing (for example classroom management, inclusion of
   quieter students, or hold etiquette on calls)? Should any dimension be merged or dropped?
6. **Overlap.** Checks for understanding and questioning quality both look at teacher questions. Are they distinct
   enough to score separately?
7. **Escalation with nothing to escalate.** Many calls need no escalation. Should those calls be marked not
   applicable, skipped, or scored another way?
8. **Incomplete recordings.** If a lesson recording stops before the end, how should recap and closure be scored?
9. **Fact sheet.** Who at the school can supply a fact sheet (fees, timings, admission dates, transport routes,
   contacts) for raters judging information accuracy?
10. **Reception categories and status values.** Are the draft lists right? Anything to add, rename or remove?
11. **Class-level numbers.** Should the report also show class-level totals such as overall student talk share or
    student question count (never per student)?
12. **Quotes required.** Is 1 or 2 quotes per score the right amount of evidence?

Notes:

&nbsp;

&nbsp;

&nbsp;

<a id="part-8"></a>

# Part 8. For schools

<a id="doc-docs-guides-recording-guide-md"></a>

## Recording guide for teachers and front-desk staff · रिकॉर्डिंग गाइड

*Source: [`docs/guides/recording-guide.md`](guides/recording-guide.md)*

> **Hindi check needed (not part of the printed guide).** The Hindi text in this guide and in
> `recording-guide.html` must be checked by a native Hindi speaker before it is sent to schools.
> (हिन्दी पाठ को स्कूलों में भेजने से पहले किसी हिन्दी भाषी व्यक्ति से जँचवाना ज़रूरी है।)

| | |
| --- | --- |
| Status | Version 0.1, October 2026 (plan task P8.3) |
| For | Teachers and front-desk (reception) staff at pilot schools, and the pilot coordinators who send it |
| Printable version | [`recording-guide.html`](guides/recording-guide.html): one A4 page, English and Hindi. Keep both files in sync. |

### For pilot coordinators: before you share this guide

1. **Fill in the school details.** The printed page has three boxes:
   - **[School name]**
   - **[Who to ask for help: name, phone]**
   - **[Consent reference / who confirms the class is covered]**: the consent reference for the class, or the
     person who can confirm that a class is covered.

   Open `recording-guide.html` in a browser (it works offline), click each highlighted box and type. Typed text is
   not saved, so print straight away, or edit the bracketed text in the file with a text editor. You can also
   print it and write the details by hand.
2. **Print** on A4 at 100% scale ("Actual size", not "Fit to page"). For a clean page, turn off the browser's
   headers and footers in the print dialog. The guide fits on one page.
3. **Call notice.** Give front-desk staff the call notice wording **your school has approved after legal review**.
   The wording in `docs/legal/drafts/call-recording-notice.md` is a draft for legal review and is not for use until
   it is approved. This guide does not repeat it on purpose.
4. **Decisions for the school** (this guide assumes the answers below; change the guide if your school decides
   differently):
   - Incoming reception calls play the notice automatically before the call connects (the draft notice assumes
     the school's phone system can do this; the school still has to confirm it).
   - A call where the notice did not play, or where the caller objected, is not uploaded to Sabha. The school's
     full process for callers who object is still open (see the call notice draft).
   - Whether outgoing reception calls are recorded at all.
   - Whether staff delete the copy on their phone after the upload is complete. This guide tells staff not to
     share recordings; it does not set a deletion rule.

---

### 1. Lessons: consent first · पीरियड: पहले सहमति

| English | हिन्दी |
| --- | --- |
| Record only a class that is covered by a consent reference. | सिर्फ़ वही क्लास रिकॉर्ड करें, जिसके लिए सहमति रेफ़रेंस हो। |
| Check with: [Consent reference / who confirms the class is covered]. | इनसे पूछें: [सहमति रेफ़रेंस / कौन बताएगा कि क्लास शामिल है]। |
| Not sure? **Do not record.** | पक्का पता न हो? **रिकॉर्ड न करें।** |
| When you upload, confirm consent in Sabha only if it is true. | अपलोड करते समय Sabha में सहमति की पुष्टि तभी करें, जब यह सच हो। |

For what parents are told and agree to, see the school's parent consent form (draft for legal review:
`docs/legal/drafts/parent-consent-form.md`). This guide does not restate it.

### 2. Do NOT record · ये रिकॉर्ड न करें

| English | हिन्दी |
| --- | --- |
| Student counselling sessions. They are not part of the pilot and need a separate legal review first. | बच्चों के काउंसलिंग सेशन। ये पायलट में नहीं हैं, इनके लिए पहले अलग से क़ानूनी जाँच ज़रूरी है। |
| Private talk: staff room, breaks, personal phone calls. | निजी बातचीत: स्टाफ़ रूम, ब्रेक, निजी फ़ोन कॉल। |
| Staff-only meetings or parent meetings, unless the school has set this up with consent. | सिर्फ़ स्टाफ़ की मीटिंग या पेरेंट्स के साथ मीटिंग, जब तक स्कूल ने सहमति लेकर इसका इंतज़ाम न किया हो। |
| Anything outside the lesson or the call. Start when it starts; stop when it ends. | पीरियड या कॉल के बाहर की कोई भी बात। पीरियड या कॉल शुरू होने पर रिकॉर्डिंग शुरू करें, ख़त्म होते ही बंद करें। |
| **Never record students to score or judge them.** Recordings are for staff feedback only. | **बच्चों को नंबर देने या परखने के लिए कभी रिकॉर्ड न करें।** रिकॉर्डिंग सिर्फ़ स्टाफ़ के फ़ीडबैक के लिए है। |

### 3. Where to put the phone · फ़ोन कहाँ रखें

| English | हिन्दी |
| --- | --- |
| 📱 Within **2 m** of the teacher, for example on the teacher's table. | 📱 टीचर से **2 मीटर** के अंदर, जैसे टीचर की टेबल पर। |
| Away from fans and AC. Their noise covers voices. | पंखे और AC से दूर। इनका शोर आवाज़ को दबा देता है। |
| Screen down, on a flat surface that does not move. | स्क्रीन नीचे करके, ऐसी सपाट जगह पर जो हिले नहीं। |
| Not in a pocket or bag. Do not cover it with books or papers. | जेब या बैग में न रखें। किताबों या काग़ज़ों से न ढकें। |

### 4. Lapel mic (optional) · लैपल माइक (अगर हो)

| English | हिन्दी |
| --- | --- |
| 🎙️ A small clip-on (lapel) mic for the phone can make the teacher's voice clearer. | 🎙️ फ़ोन के लिए छोटा क्लिप वाला (लैपल) माइक टीचर की आवाज़ और साफ़ कर सकता है। |
| Clip it to your collar. Keep it away from dupatta, scarf, ID card and jewellery: rubbing makes noise. | इसे कॉलर पर लगाएँ। दुपट्टे, स्कार्फ़, ID कार्ड और गहनों से दूर रखें: रगड़ से शोर होता है। |
| Do a test recording with the mic before the first lesson. | पहले पीरियड से पहले माइक के साथ एक टेस्ट रिकॉर्डिंग कर लें। |

### 5. Before you start · शुरू करने से पहले

| English | हिन्दी |
| --- | --- |
| ✈️ Turn on **airplane mode** or Do Not Disturb. Calls and notifications can stop the recording or add noise. | ✈️ **एयरप्लेन मोड** या डू नॉट डिस्टर्ब (DND) चालू करें। कॉल और नोटिफ़िकेशन से रिकॉर्डिंग रुक सकती है या शोर आ सकता है। |
| 🔋 Charge the phone fully before you start. | 🔋 शुरू करने से पहले फ़ोन पूरा चार्ज कर लें। |
| 💾 Check that the phone has enough free space. Move or delete old files you no longer need. | 💾 देख लें कि फ़ोन में काफ़ी जगह (स्टोरेज) ख़ाली है। जिन पुरानी फ़ाइलों की ज़रूरत नहीं, उन्हें हटा दें। |
| 🎧 Do a short test with the screen off, then play it back. This checks that the app keeps recording. | 🎧 स्क्रीन बंद करके छोटी-सी टेस्ट रिकॉर्डिंग करें, फिर सुनें। इससे पता चलता है कि ऐप रिकॉर्ड करता रहता है। |

### 6. Upload the original file · ओरिजिनल फ़ाइल अपलोड करें

| English | हिन्दी |
| --- | --- |
| ⬆️ Turn airplane mode off. Upload the original file **directly in Sabha**, from the phone or a computer. | ⬆️ एयरप्लेन मोड बंद करें। ओरिजिनल फ़ाइल **सीधे Sabha में** अपलोड करें, फ़ोन से या कंप्यूटर से। |
| ⛔ **Do not send it through WhatsApp first.** WhatsApp compresses the audio again and the sound gets worse. | ⛔ **पहले WhatsApp पर न भेजें।** WhatsApp आवाज़ को दोबारा कम्प्रेस करता है, जिससे आवाज़ ख़राब हो जाती है। |
| Do not edit, cut or convert the file. One lesson or one call = one file. | फ़ाइल को एडिट, कट या कन्वर्ट न करें। एक पीरियड या एक कॉल = एक फ़ाइल। |
| 📁 Sabha accepts **mp3, m4a, wav, ogg, webm and mp4** files, up to **1 GB** each, from **30 seconds to 3 hours** long. | 📁 Sabha ये फ़ाइलें लेता है: **mp3, m4a, wav, ogg, webm और mp4**, हर फ़ाइल **1 GB** तक, **30 सेकंड से 3 घंटे** तक लंबी। |
| A file that is too big or too long? Ask [Who to ask for help: name, phone]. | फ़ाइल बहुत बड़ी या बहुत लंबी है? [मदद के लिए: नाम, फ़ोन] से पूछें। |
| Do not share the recording with anyone. | रिकॉर्डिंग किसी से शेयर न करें। |

The file limits come from the upload rules in `docs/prompts/week-1.md` (P2.1: formats and 1 GB) and
`docs/prompts/week-2.md` (P3.2: 30 seconds to 3 hours). Update this guide if those limits change.

### 7. Front desk: the call notice · फ़्रंट डेस्क: कॉल का नोटिस

| English | हिन्दी |
| --- | --- |
| 📞 The recording notice **must play, or be read out, before a call is recorded.** | 📞 **कॉल रिकॉर्ड होने से पहले रिकॉर्डिंग का नोटिस चलना, या पढ़कर सुनाया जाना, ज़रूरी है।** |
| Incoming calls: the notice plays before the call connects. | आने वाली कॉल: नोटिस कॉल जुड़ने से पहले चलता है। |
| Calls you make (only if your school records them): read the notice first, before anything else. | आप जो कॉल करें (सिर्फ़ अगर स्कूल उन्हें रिकॉर्ड करता है): कोई और बात करने से पहले नोटिस पढ़ें। |
| Use only the wording your school has approved, never a draft. | सिर्फ़ स्कूल का मंज़ूर किया हुआ नोटिस इस्तेमाल करें, कोई ड्राफ़्ट नहीं। |
| The notice did not play, or the caller said no? **Do not upload that call.** Tell [Who to ask for help: name, phone]. | नोटिस नहीं चला, या कॉल करने वाले ने मना किया? **वह कॉल अपलोड न करें।** [मदद के लिए: नाम, फ़ोन] को बताएँ। |
| Sabha cannot use calls shorter than 30 seconds. | 30 सेकंड से छोटी कॉल Sabha में इस्तेमाल नहीं हो सकती। |

The approved notice wording comes from the school after legal review. The draft is in
`docs/legal/drafts/call-recording-notice.md` and is not for use until it is approved.

### Help · मदद

| English | हिन्दी |
| --- | --- |
| School: [School name] | स्कूल: [स्कूल का नाम] |
| Questions or problems: [Who to ask for help: name, phone] | सवाल या दिक़्क़त: [मदद के लिए: नाम, फ़ोन] |

<a id="part-9"></a>

# Part 9. Legal drafts (waiting for the law team)

<a id="doc-docs-legal-drafts-call-recording-notice-md"></a>

## Spoken recording notice for school reception calls

*Source: [`docs/legal/drafts/call-recording-notice.md`](legal/drafts/call-recording-notice.md)*

**DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE**


| | |
| --- | --- |
| Status | Draft v0.1 for legal review (plan task P8.1). Not for use until approved. |
| Date | 14 October 2026 |
| Prepared by | Sabha product team, Schoollog [legal entity name] |
| For review by | [Lawyer name / firm] |

**Notes for reviewers (remove before use):**

- Text in [square brackets] is a placeholder or a decision for the school or the lawyer.
- References such as "Q-G" point to the matching section of `questions-for-lawyer.md`.
- **Hindi text:** must be checked by a native Hindi speaker as well as by the lawyer before use.
  (हिन्दी पाठ को इस्तेमाल से पहले किसी हिन्दी भाषी व्यक्ति और वकील, दोनों से जँचवाना ज़रूरी है।)
- Word counts below count "[School name]" as one word. Timings are rough estimates from the word count at a
  calm speaking pace; time the actual recorded message before use.

---

#### Variant A: standard (about 10 seconds)

| Language | Text | Words |
| --- | --- | --- |
| English | Welcome to [School name]. To help our staff improve, this call will be recorded and analysed. [If you do not want this, please tell us.] | 24 |
| हिन्दी | [स्कूल का नाम] में आपका स्वागत है। स्टाफ़ की सेवा बेहतर बनाने के लिए यह कॉल रिकॉर्ड करके जाँची जाएगी। [आप ऐसा न चाहें, तो हमें बताइए।] | 25 |

#### Variant B: shorter (about 7 seconds)

| Language | Text | Words |
| --- | --- | --- |
| English | This call will be recorded and analysed to help our staff improve. [Please tell us if you object.] | 18 |
| हिन्दी | स्टाफ़ की सेवा बेहतर बनाने के लिए यह कॉल रिकॉर्ड करके जाँची जाएगी। [आपत्ति हो, तो बताइए।] | 17 |

The last sentence of each variant (in brackets) depends on the school's process for callers who object (see
below). If the school offers a keypad option instead, replace it with, for example:

| Language | Alternative last sentence | Words |
| --- | --- | --- |
| English | To continue without recording, press 1. | 6 |
| हिन्दी | रिकॉर्डिंग के बिना बात करने के लिए 1 दबाइए। | 9 |

Notes on the wording:

- "Analysed" (Hindi: "जाँची जाएगी", "will be checked") is included because calls are analysed by software,
  including an AI model, to produce feedback for the receptionist. Whether the notice must say more (for example
  that AI is used, who Schoollog is, or where to find a fuller privacy notice) is a question for the lawyer (Q-G).
- The notice says "will be recorded", not "may be recorded", because every call on a covered line is recorded.
  [School to confirm.]

---

#### Where the notice plays

- **Incoming calls:** played automatically **before the call connects** to the receptionist, by [the school's
  phone system / IVR provider, to be confirmed]. [School to confirm that its phone system can play a message
  before connecting.]
- **Language order:** [School to choose: Hindi then English, English then Hindi, or one language per line.]
  Playing Variant A in both languages takes about 20 seconds; playing Variant B in both takes about 14 seconds.
- **Outgoing calls made by reception:** [School to decide: are outgoing calls recorded? If yes, the receptionist
  reads Variant B at the start of the call, before discussing anything else.]
- **Transferred calls:** [School to decide whether recording continues after a call is transferred to another
  staff member, and whether that person is covered by the staff notice.]
- **Fuller information:** [Optional: a link or place where callers can read more, e.g. the school website
  privacy notice at (URL). Lawyer to advise whether this is needed.]

#### If the caller objects

> **[QUESTION FOR THE SCHOOL AND THE LAWYER: the school's process is not yet decided.]**
>
> Options to consider:
>
> - (a) The caller can **continue without recording**: they press a key or tell the receptionist, and the
>   recording is stopped. Needs phone-system support.
> - (b) The call is recorded by the phone system but is **never uploaded to Sabha**, and the recording is deleted
>   [within (N) days / immediately]. The receptionist marks the call as "caller objected" [where, to be decided].
> - (c) The caller is offered **another way to reach the school** that is not recorded (for example email,
>   [WhatsApp number], or a visit).
> - (d) [Other, to be specified by the school.]
>
> Questions: is any of these enough? Is a notice enough, or does the caller's consent need to be recorded? What if
> the caller is a child? See Q-G.

> Drafting note for Schoollog: Sabha holds consent records per call line, not per call. There is currently no
> per-call "caller objected" marker in the product. Whichever option is chosen, Schoollog needs to confirm how an
> objected call is kept out of processing and deleted.

<a id="doc-docs-legal-drafts-parent-consent-form-md"></a>

## Parent consent form: recording classroom lessons for teacher development

*Source: [`docs/legal/drafts/parent-consent-form.md`](legal/drafts/parent-consent-form.md)*

**DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE**


| | |
| --- | --- |
| Status | Draft v0.1 for legal review (plan task P8.1). Not for use with parents until approved. |
| Date | 14 October 2026 |
| Prepared by | Sabha product team, Schoollog [legal entity name] |
| For review by | [Lawyer name / firm] |
| Scope | Classroom lessons only. Reception calls are covered by `call-recording-notice.md`. Student counselling sessions are out of scope and must not be recorded under this form. |

**Notes for reviewers (remove before use):**

- Text in [square brackets] is a placeholder or a decision for the school or the lawyer.
- Lines marked "Drafting note" are for reviewers and are not part of the form.
- References such as "Q-A" point to the matching section of `questions-for-lawyer.md`.
- **Hindi text:** the Hindi column must be checked by a native Hindi speaker as well as by the lawyer before use.
  (हिन्दी कॉलम को इस्तेमाल से पहले किसी हिन्दी भाषी व्यक्ति और वकील, दोनों से जँचवाना ज़रूरी है।)

---

#### 1. About this form · इस फ़ॉर्म के बारे में

| English | हिन्दी |
| --- | --- |
| [School name] would like to record the sound of some lessons in your child's class. | [स्कूल का नाम] आपके बच्चे की क्लास में कुछ पीरियड (लेसन) की आवाज़ रिकॉर्ड करना चाहता है। |
| The recordings are used to give feedback to our teachers, so that they can keep improving their teaching. | इन रिकॉर्डिंग से हमारे टीचरों को अपने पढ़ाने के तरीक़े पर फ़ीडबैक दिया जाता है, ताकि वे और अच्छा पढ़ा सकें। |
| The recordings are about the teacher's teaching, not about your child. | ये रिकॉर्डिंग टीचर के पढ़ाने के बारे में हैं, आपके बच्चे के बारे में नहीं। |
| We are asking for your permission (consent) under India's Digital Personal Data Protection Act, 2023. | भारत के डिजिटल पर्सनल डेटा प्रोटेक्शन एक्ट, 2023 के तहत हम आपकी अनुमति (सहमति) माँग रहे हैं। |
| Please read this form, then tick Yes or No in section 10 and sign it. | कृपया यह फ़ॉर्म पढ़ें, फिर भाग 10 में "हाँ" या "नहीं" पर निशान लगाएँ और हस्ताक्षर करें। |

#### 2. What is recorded · क्या रिकॉर्ड होगा

| English | हिन्दी |
| --- | --- |
| Only sound (audio) is recorded. No video is recorded and no photos are taken. | सिर्फ़ आवाज़ (ऑडियो) रिकॉर्ड होगी। कोई वीडियो नहीं बनेगा और कोई फ़ोटो नहीं ली जाएगी। |
| The phone or microphone is kept near the teacher. | फ़ोन या माइक्रोफ़ोन टीचर के पास रखा जाता है। |
| Your child's voice may still be recorded, for example when they answer a question, read aloud or talk in class. | फिर भी आपके बच्चे की आवाज़ रिकॉर्ड हो सकती है, जैसे जब वह किसी सवाल का जवाब देता/देती है, कुछ पढ़कर सुनाता/सुनाती है, या क्लास में बात करता/करती है। |
| If a student's name is spoken in class, it may also be recorded. | अगर क्लास में किसी बच्चे का नाम लिया जाता है, तो वह भी रिकॉर्ड हो सकता है। |
| Which lessons and how often: [School to fill in, e.g. up to N lessons per teacher per month]. | कौन-से पीरियड और कितनी बार: [स्कूल भरेगा, जैसे हर टीचर के महीने में ज़्यादा से ज़्यादा N पीरियड]। |

#### 3. Why we record, and what we will not do · हम रिकॉर्ड क्यों करते हैं, और क्या नहीं करेंगे

| English | हिन्दी |
| --- | --- |
| **Purpose:** to give feedback to teachers and support their development as teachers. This is the only purpose. | **मक़सद:** टीचरों को फ़ीडबैक देना और उन्हें बेहतर टीचर बनने में मदद करना। रिकॉर्डिंग का बस यही मक़सद है। |
| We will **not** give your child any score, grade, mark or rating from these recordings. | इन रिकॉर्डिंग से आपके बच्चे को कोई स्कोर, ग्रेड, नंबर या रेटिंग **नहीं** दी जाएगी। |
| We will **not** build a profile of your child, track your child, or monitor your child's behaviour. | हम आपके बच्चे की कोई प्रोफ़ाइल **नहीं** बनाएँगे, न उस पर नज़र रखेंगे, न उसके व्यवहार की निगरानी करेंगे। |
| We will **not** try to identify which student is speaking. The software labels speakers only as "Teacher" or "Student(s)". No student is labelled by name. | हम यह पहचानने की कोशिश **नहीं** करेंगे कि कौन-सा बच्चा बोल रहा है। सॉफ़्टवेयर बोलने वालों को सिर्फ़ "Teacher" (टीचर) या "Student(s)" (बच्चे) लिखकर दिखाता है। किसी भी बच्चे को नाम से नहीं दिखाया जाता। |
| The recordings will **not** be used for any decision about your child, for example marks, discipline or admission. | इन रिकॉर्डिंग का इस्तेमाल आपके बच्चे के बारे में कोई भी फ़ैसला लेने के लिए **नहीं** होगा, जैसे नंबर, अनुशासन या एडमिशन। |

> Drafting note: Schoollog and the school to confirm whether to add "Recordings and transcripts will not be used
> to train AI models or for advertising." Include it only if Schoollog can confirm it, including for every AI
> provider it uses. See Q-E.

#### 4. What happens to a recording · रिकॉर्डिंग के साथ क्या होता है

| English | हिन्दी |
| --- | --- |
| 1. The teacher records the lesson and uploads the audio file to Sabha, a software service that Schoollog provides to the school. | 1. टीचर पीरियड रिकॉर्ड करके ऑडियो फ़ाइल Sabha (सभा) पर अपलोड करते हैं। Sabha एक सॉफ़्टवेयर सेवा है, जो Schoollog (स्कूललॉग) कंपनी स्कूल को देती है। |
| 2. The software turns the speech into written text (a "transcript") and marks which parts were spoken by the teacher and which by students. | 2. सॉफ़्टवेयर बोली गई बातों को लिखित रूप ("ट्रांसक्रिप्ट") में बदलता है, और यह दिखाता है कि कौन-सा हिस्सा टीचर ने बोला और कौन-सा बच्चों ने। |
| 3. Before the text is checked by an AI (artificial intelligence) service, we use software to hide phone numbers, ID numbers (such as Aadhaar or PAN), email addresses and students' names. The AI service gets only this written text, never the audio. | 3. AI (आर्टिफ़िशियल इंटेलिजेंस) सेवा से जाँच करवाने से पहले, हम सॉफ़्टवेयर की मदद से फ़ोन नंबर, पहचान नंबर (जैसे आधार या पैन), ईमेल पते और बच्चों के नाम छिपा देते हैं। AI सेवा को सिर्फ़ यही लिखित टेक्स्ट मिलता है, ऑडियो कभी नहीं। |
| 4. The teacher's teaching is then reviewed against a fixed checklist (a "rubric"), for example how the teacher asks questions and how much chance the class gets to speak. | 4. फिर एक तय चेकलिस्ट ("रूब्रिक") के हिसाब से टीचर के पढ़ाने के तरीक़े को परखा जाता है, जैसे टीचर सवाल कैसे पूछते हैं और क्लास को बोलने का कितना मौक़ा मिलता है। |
| 5. The teacher and the school's academic leaders receive a feedback report about the teacher. | 5. टीचर और स्कूल के एकेडमिक लीडर्स को टीचर के बारे में एक फ़ीडबैक रिपोर्ट मिलती है। |

> Drafting note: the hiding (masking) of names and numbers is automated and may not catch everything. Student
> names are masked from a configurable list of names; staff names are not masked by default. See Q-B and Q-E.

#### 5. Who can see the recordings and reports · रिकॉर्डिंग और रिपोर्ट कौन देख सकता है

| English | हिन्दी |
| --- | --- |
| The teacher who was recorded (only their own recordings and reports). | जिस टीचर की रिकॉर्डिंग हुई है (सिर्फ़ अपनी रिकॉर्डिंग और रिपोर्ट)। |
| The school staff who guide that teacher: [School to list the exact roles, e.g. academic head, coordinator, principal]. | स्कूल के वे लोग जो उस टीचर का मार्गदर्शन करते हैं: [स्कूल सही पद लिखेगा, जैसे एकेडमिक हेड, कोऑर्डिनेटर, प्रिंसिपल]। |
| Schoollog [legal entity name], the service provider that processes the recordings for the school. Only Schoollog staff who have been given permission can access the data, and only when needed to run or fix the service. [Schoollog to confirm.] | Schoollog [कंपनी का क़ानूनी नाम], जो स्कूल की ओर से रिकॉर्डिंग को प्रोसेस करने वाली सेवा देती है। Schoollog के सिर्फ़ वही कर्मचारी डेटा देख सकते हैं जिन्हें इसकी इजाज़त दी गई है, और वो भी सिर्फ़ तब जब सेवा चलाने या कोई तकनीकी दिक़्क़त ठीक करने के लिए ज़रूरी हो। [Schoollog पुष्टि करेगा।] |
| The AI service [provider name, to be confirmed] receives only the written text, with students' names and personal numbers hidden. It does not receive the audio. | AI सेवा [कंपनी का नाम, अभी तय होना है] को सिर्फ़ लिखित टेक्स्ट मिलता है, जिसमें बच्चों के नाम और निजी नंबर छिपे होते हैं। उसे ऑडियो नहीं मिलता। |
| Parents and students cannot see the recordings or reports. They are not shared with anyone else [unless required by law; lawyer to confirm wording]. | माता-पिता और बच्चे रिकॉर्डिंग या रिपोर्ट नहीं देख सकते। इन्हें किसी और के साथ साझा नहीं किया जाता [जब तक क़ानूनन ज़रूरी न हो; वकील शब्दों की पुष्टि करेंगे]। |
| Each time someone plays a recording or exports a report, the software keeps a record of who did it and when. | जब भी कोई रिकॉर्डिंग चलाता है या रिपोर्ट एक्सपोर्ट करता है, सॉफ़्टवेयर यह रिकॉर्ड रखता है कि किसने और कब किया। |
| [OPTIONAL, to be decided by the school, Schoollog and the lawyer: "A small number of recordings may be listened to by trained reviewers working for Schoollog, to check that transcripts and feedback are accurate. They follow the same rules: no scores for students and no identifying students."] | [वैकल्पिक, स्कूल, Schoollog और वकील तय करेंगे: "कुछ गिनी-चुनी रिकॉर्डिंग Schoollog के लिए काम करने वाले ट्रेनिंग पाए हुए लोग (रिव्यूअर) सुन सकते हैं, यह जाँचने के लिए कि ट्रांसक्रिप्ट और फ़ीडबैक सही हैं। वे भी इन्हीं नियमों का पालन करते हैं: बच्चों को कोई स्कोर नहीं, और किसी बच्चे की पहचान नहीं।"] |

> Drafting note: the optional row reflects how Schoollog plans to check transcript and scoring quality (human
> annotators and raters working on a sample of recordings). If it applies, it is a use beyond "teacher feedback"
> and probably needs to be stated. See Q-J. The wording used for Schoollog's role in this section depends on the
> answer to Q-C.

#### 6. Where the data is stored · डेटा कहाँ रखा जाता है

| English | हिन्दी |
| --- | --- |
| Recordings, transcripts and reports are stored on servers in India, in the Mumbai region of Amazon Web Services (AWS, region "ap-south-1"). | रिकॉर्डिंग, ट्रांसक्रिप्ट और रिपोर्ट भारत में, Amazon Web Services (AWS) के मुंबई रीजन ("ap-south-1") के सर्वरों पर रखी जाती हैं। |
| [If the AI service processes the text outside India, this must be stated here, with the country. See drafting note.] | [अगर AI सेवा टेक्स्ट को भारत के बाहर प्रोसेस करती है, तो यह बात देश के नाम के साथ यहाँ लिखी जाएगी।] |
| How the data is protected: [Schoollog to describe its security measures in plain words. Include only measures that are in place.] | डेटा की सुरक्षा कैसे होती है: [Schoollog अपने सुरक्षा उपाय आसान शब्दों में लिखेगा। सिर्फ़ वही उपाय लिखे जाएँ जो सच में लागू हैं।] |

> Drafting note: the database is planned on MongoDB Atlas (Mumbai) and files on AWS S3 (ap-south-1). Schoollog
> to confirm the full list of places where data is stored or processed, including the speech-to-text servers,
> before this section is final. See Q-C and Q-E.

#### 7. How long we keep it · हम इसे कितने समय तक रखते हैं

| English | हिन्दी |
| --- | --- |
| Audio recordings: deleted automatically after 90 days [School to confirm, or state a shorter period]. | ऑडियो रिकॉर्डिंग: 90 दिन बाद अपने-आप डिलीट (मिटा दी) हो जाती हैं [स्कूल पुष्टि करेगा, या कम समय लिखेगा]। |
| Written transcripts and the teacher's feedback reports: kept for [period, to be decided by the school and the lawyer]. | लिखित ट्रांसक्रिप्ट और टीचर की फ़ीडबैक रिपोर्ट: [कितने समय तक, स्कूल और वकील तय करेंगे] तक रखी जाती हैं। |
| Backup copies (kept to recover data after a technical failure) are removed after [period, Schoollog to confirm]. | बैकअप कॉपी (जो तकनीकी ख़राबी के बाद डेटा वापस लाने के लिए रखी जाती हैं) [अवधि, Schoollog पुष्टि करेगा] बाद हटा दी जाती हैं। |

#### 8. Your choice, and withdrawing consent · आपकी मर्ज़ी, और सहमति वापस लेना

| English | हिन्दी |
| --- | --- |
| Giving consent is your choice. Saying No will not affect your child's studies, marks or treatment at school in any way. | सहमति देना या न देना आपकी मर्ज़ी है। "नहीं" कहने से आपके बच्चे की पढ़ाई, नंबर या स्कूल में उसके साथ होने वाले बर्ताव पर कोई असर नहीं पड़ेगा। |
| If you say No: [School to explain what it will do. Options are listed in Q-A.] | अगर आप "नहीं" कहते हैं: [स्कूल बताएगा कि वह क्या करेगा।] |
| You can withdraw your consent at any time, as easily as you gave it, by [method, e.g. telling the class teacher, writing to the grievance officer in section 9, or using (form / app)]. | आप जब चाहें अपनी सहमति वापस ले सकते हैं, उतनी ही आसानी से जितनी आसानी से आपने दी थी: [तरीक़ा, जैसे क्लास टीचर को बताकर, भाग 9 में दिए शिकायत अधिकारी को लिखकर, या (फ़ॉर्म / ऐप) से]। |
| After you withdraw, [School to describe, e.g. no new lessons in your child's class will be recorded] within [N working days]. | सहमति वापस लेने के बाद, [N कामकाजी दिनों] के अंदर [स्कूल बताएगा, जैसे आपके बच्चे की क्लास में कोई नया पीरियड रिकॉर्ड नहीं होगा]। |
| Recordings already made: because the software does not identify individual students, we cannot remove only your child's voice from a recording. [School and lawyer to decide: (a) on your request, we delete the recordings of your child's class made before you withdrew; or (b) they are deleted on the normal schedule in section 7.] | जो रिकॉर्डिंग पहले हो चुकी हैं: सॉफ़्टवेयर किसी एक बच्चे को नहीं पहचानता, इसलिए हम किसी रिकॉर्डिंग में से सिर्फ़ आपके बच्चे की आवाज़ नहीं हटा सकते। [स्कूल और वकील तय करेंगे: (क) आपके कहने पर, सहमति वापस लेने से पहले की आपके बच्चे की क्लास की रिकॉर्डिंग डिलीट कर दी जाएँगी; या (ख) वे भाग 7 में बताए गए सामान्य समय पर डिलीट होंगी।] |
| This consent is for the school year [20XX–20XX], unless you withdraw it earlier. | यह सहमति [20XX–20XX] सत्र के लिए है, जब तक आप इसे पहले वापस न ले लें। |

#### 9. Questions, requests and complaints · सवाल, अनुरोध और शिकायत

| English | हिन्दी |
| --- | --- |
| To ask a question, withdraw consent, ask for deletion or make a complaint, contact our grievance officer: [Name], [Email], [Phone], [Office address and hours]. | कोई सवाल पूछने, सहमति वापस लेने, डेटा डिलीट करवाने या शिकायत करने के लिए हमारे शिकायत अधिकारी से संपर्क करें: [नाम], [ईमेल], [फ़ोन], [दफ़्तर का पता और समय]। |
| School: [School name], [Address]. | स्कूल: [स्कूल का नाम], [पता]। |
| Service provider: Schoollog [legal entity name], [Address], [Contact email]. | सेवा देने वाली कंपनी: Schoollog [कंपनी का क़ानूनी नाम], [पता], [संपर्क ईमेल]। |
| We will reply within [N days; lawyer to confirm]. | हम [N दिनों; वकील पुष्टि करेंगे] के अंदर जवाब देंगे। |
| If you are not satisfied with our reply, you can [escalation route; lawyer to confirm, e.g. complain to the Data Protection Board of India]. | अगर आप हमारे जवाब से संतुष्ट नहीं हैं, तो आप [आगे शिकायत का रास्ता; वकील पुष्टि करेंगे, जैसे डेटा प्रोटेक्शन बोर्ड ऑफ़ इंडिया में शिकायत] कर सकते हैं। |

> Drafting note: lawyer to confirm which rights must be listed in this section and how. See Q-H and Q-I.

#### 10. Consent · सहमति

Please tick only one box: Yes or No. · कृपया सिर्फ़ एक बॉक्स पर निशान लगाएँ: "हाँ" या "नहीं"।

| English | हिन्दी |
| --- | --- |
| Parent or guardian name: ______________________ | माता-पिता या अभिभावक का नाम: ______________________ |
| Relationship to the student: ☐ Mother ☐ Father ☐ Legal guardian | बच्चे से रिश्ता: ☐ माँ ☐ पिता ☐ क़ानूनी अभिभावक |
| Student name: ______________________ | बच्चे का नाम: ______________________ |
| Class and section: ____________ | क्लास और सेक्शन: ____________ |
| [Mobile number or email for verification: include only if the lawyer recommends it; see Q-A] | [पुष्टि के लिए मोबाइल नंबर या ईमेल: सिर्फ़ तभी, जब वकील कहें] |
| I have read this form, or it has been explained to me. | मैंने यह फ़ॉर्म पढ़ लिया है, या मुझे समझा दिया गया है। |
| ☐ **Yes**, I agree to lessons in my child's class being recorded and used as described in this form. | ☐ **हाँ**, मैं सहमत हूँ कि मेरे बच्चे की क्लास के पीरियड इस फ़ॉर्म में बताए गए तरीक़े से रिकॉर्ड और इस्तेमाल किए जाएँ। |
| ☐ **No**, I do not agree. | ☐ **नहीं**, मैं सहमत नहीं हूँ। |
| Date: ____________ | तारीख़: ____________ |
| Signature: ______________________ | हस्ताक्षर: ______________________ |

**For school use only · सिर्फ़ स्कूल के इस्तेमाल के लिए**

| English | हिन्दी |
| --- | --- |
| Received by (name and role): ______________ Date: ________ | किसने लिया (नाम और पद): ______________ तारीख़: ________ |
| Consent reference number: ______________ | सहमति रेफ़रेंस नंबर: ______________ |
| How the parent's identity was checked: [method, see Q-A] | माता-पिता की पहचान की पुष्टि कैसे हुई: [तरीक़ा] |

> Drafting note: the consent reference number links this form to the consent record in Sabha. Sabha is designed
> so that a recording is not processed unless it is covered by a valid consent record for that class or section
> and school year.

<a id="doc-docs-legal-drafts-questions-for-lawyer-md"></a>

## Questions for legal review: Sabha pilot in schools

*Source: [`docs/legal/drafts/questions-for-lawyer.md`](legal/drafts/questions-for-lawyer.md)*

**DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE**


| | |
| --- | --- |
| Status | Draft v0.1 (plan task P8.1) |
| Date | 14 October 2026 |
| Prepared by | Sabha product team, Schoollog [legal entity name] |
| For | [Lawyer name / firm] |
| Enclosed drafts | `parent-consent-form.md`, `staff-consent-and-notice.md`, `call-recording-notice.md` |

We are preparing an 8-week pilot of Sabha in [N] schools in India, covering classroom lessons and school
reception calls. We would like your advice under India's Digital Personal Data Protection Act, 2023, and any
other law you think is relevant, before anything is recorded. The enclosed drafts are our first attempt and are
not final.

Each group below starts with a short description of how the product works, then lists our questions. Question
numbers (A1, B2, ...) are referenced from the drafts. The descriptions reflect the product as designed for the
pilot; Schoollog will confirm before go-live that the running system matches them. Text in [square brackets] is
not yet known or decided.

---

#### How Sabha works (summary)

- **Customers.** Each school is a separate customer account. One school's data is kept separate from every
  other school's.
- **What is recorded.** Classroom lessons: audio only, on a phone or small microphone near the teacher.
  Reception calls: recorded by the school's phone system [mechanism and vendor to be confirmed] and then uploaded.
- **Consent gate.** Every recording must be linked to a consent record held in Sabha. A consent record has a scope
  (a class or section for a school year, a staff member, or a call line), valid-from and valid-to dates, and a
  link to the signed document. A recording without a valid consent record is not processed.
- **Storage.** Files are uploaded directly to storage in AWS Mumbai (ap-south-1). The database is planned on
  MongoDB Atlas, Mumbai. Product rule: data stays in India unless an exception is explicitly approved.
- **Speech processing.** The software removes silence (while keeping original timings), separates speakers, and
  labels them by role only: "Teacher" and "Student(s)", or "Receptionist" and "Caller". It never identifies
  individual students. Speech-to-text runs on servers Schoollog operates [location to be confirmed: AWS Mumbai or
  Schoollog's own server at (location)]. Audio is not sent to outside speech-to-text companies [to be confirmed].
- **Analysis.** Some measures are computed directly by software (for lessons: teacher and student talk share,
  number of questions, pace, silences, longest teacher monologue; for calls: call length, hold or silent gaps,
  caller talk share). An AI language model then rates the staff member against a rubric. Before any text goes to
  the AI provider, software masks phone numbers, Aadhaar-like and PAN-like numbers, emails, and student names from
  a configured list. Staff names are not masked by default. Every AI judgement must quote the transcript with
  timestamps; the software checks each quote exists, and judgements that fail this check are not shown.
- **Who sees what.** Staff see only their own reports and can dispute any score. Reviewers and managers see their
  section or unit. School administrators see everything for their school, including some measures marked
  "Internal" that have not yet passed quality checks. Parents and students have no access. Every playback, export
  and score change is logged.
- **Retention and erasure.** Audio is deleted automatically after 90 days by default (a per-school setting).
  Transcripts, scores and reports are currently kept with no end date set. An erasure function deletes data for a
  recording, a staff member or a whole school, and keeps a minimal record that the erasure happened.
- **Other services used to run the product.** [To be confirmed, with hosting region and what data each receives:
  error monitoring (Sentry), AI call tracing (Langfuse, which stores AI inputs and outputs), email notifications
  (Amazon SES).]

---

#### A. Verifiable parental consent

**Context.** The school would give each parent the form in English and Hindi, [on paper, collected by the class
teacher / through the school's existing parent communication channel; to be decided]. One form per student per
school year. In Sabha, consent is recorded per class or section. Recording a lesson captures every student who
speaks, so a class can only be recorded if consent covers the class.

- **A1.** What would you consider an adequate mechanism for obtaining verifiable consent from a parent or lawful
  guardian? Is a signed paper form collected by the school enough, or is an identity check needed (for example
  matching against admission records, or a one-time code sent to the parent's registered mobile number)?
- **A2.** What record of the consent and of the identity check should the school keep, and for how long?
- **A3.** Do we need consent from every parent in a class before recording that class? If one parent says No,
  which options are acceptable: (a) do not record that class at all; (b) record only lessons where that student is
  absent; (c) [other]? We do not think seating a student away from the microphone is reliable.
- **A4.** Can consent be collected once per school year? Can it be included in annual or admission paperwork, or
  should it be a separate form?
- **A5.** For students aged 18 or over in senior classes, should we ask the student instead of the parent? Should
  younger students also be told about the recording, in age-appropriate words?
- **A6.** Is English and Hindi enough, or should the form be available in other languages that parents at a
  school use?
- **A7.** Is the content of the parent form adequate as a notice? What is missing, and which rights must be
  listed?

#### B. Children's data obligations

**Context.** Staff are analysed, not students. There are no student-level scores, profiles or identification,
and no tracking or behavioural monitoring of children. However, students' voices and words are captured
incidentally. Transcripts stored in Sabha contain what students say, and may contain names spoken in class. Names
are masked before text goes to the AI provider; the mapping is kept on our servers so authorised staff see the
original wording. Some lesson measures are about the class as a group (for example the share of lesson time
students speak). Masking student names needs a list of names [how this list is obtained is to be confirmed, e.g.
a class list from the school]. Audio is deleted after 90 days; transcripts are kept longer [period not set].

- **B1.** Does the incidental capture of students' voices and words in lesson audio and transcripts count as
  processing children's personal data, even though we never identify which student is speaking?
- **B2.** Are there restrictions on processing children's data (for example on tracking, behavioural monitoring or
  targeted advertising) that apply here? Does our design, or do the class-level measures, raise any concern under
  them?
- **B3.** Are there exemptions or special conditions for educational institutions that might apply to this use?
  Would they change the consent approach?
- **B4.** If the school gives Schoollog a list of student names only so that they can be masked, does that create
  any further obligation?
- **B5.** Should student names also be masked in the transcripts stored in Sabha, not only in the text sent to the
  AI provider?
- **B6.** Should the parent form promise "no AI model training and no advertising"? If so, what commitments do we
  need from AI providers to make that promise?
- **B7.** Student counselling sessions are out of scope for the pilot. Please confirm they should not be recorded
  without a separate review.

#### C. Roles of the school and Schoollog, and the contract between them

**Context.** The school decides to use Sabha, decides which lessons and calls are recorded, collects consent,
sets the audio retention period, reads reports and manages staff accounts. Schoollog provides and hosts the
software, chooses the cloud and AI providers, designs the default rubrics (agreed with each school), provides
technical support, and plans to use a sample of recordings to check transcript and scoring quality (see J).

- **C1.** Is the school the data fiduciary and Schoollog a data processor? Does any of Schoollog's own activity
  (choosing providers, designing rubrics, quality checking) make it a data fiduciary, alone or jointly, for some
  purposes? Which ones?
- **C2.** What contract is needed between the school and Schoollog, and what should it cover? For example:
  processing only on the school's instructions, confidentiality, security measures, use of other providers,
  data location, breach notice to the school (timeline and content), help with parents' and staff requests,
  deletion or return of data at the end, audit rights, liability.
- **C3.** How should other providers be disclosed and approved: AWS (Mumbai), MongoDB Atlas (Mumbai), the AI
  provider [not yet chosen], [error monitoring, AI call tracing, email: to be confirmed]? Does each school need to
  approve each one, and how are changes handled?
- **C4.** The phone system that records reception calls belongs to the school [vendor to be confirmed]. Does that
  vendor need any agreement with the school or with Schoollog?
- **C5.** Could either the school or Schoollog be treated as a significant data fiduciary? What would change?
- **C6.** Is a shorter pilot agreement acceptable for the 8-week pilot, or should the full contract be in place
  from the first recording?

#### D. Retention periods

**Context.** Audio: deleted automatically after 90 days by default (per-school setting); after 30 days it moves to
a cheaper storage tier but is still stored. Playback copies are deleted with the audio. Transcripts, analyses,
scores, disputes and the access log: kept, no period set yet. Backups: continuous database backup [retention
window to be confirmed] and a nightly export to a separate backup store with file versioning [period to be
confirmed]. After an erasure, a minimal record of the erasure is kept. A fixed set of recordings may be kept for
quality evaluation (see J).

- **D1.** Is 90 days a reasonable default for audio, given that it contains children's voices? Should it be
  shorter?
- **D2.** What retention periods would you advise for transcripts, scores and reports, disputes, and the access
  log?
- **D3.** Is it acceptable that deleted data remains in backups until the backups expire, if that period is stated
  in the forms? What period would you consider reasonable?
- **D4.** Should anything be deleted when a student leaves the school, or when a staff member leaves employment?
- **D5.** At the end of the contract, what should happen to the school's data, and how fast?
- **D6.** Is there any other law that requires the school or Schoollog to keep any of these records for a minimum
  period?

#### E. Cross-border transfer for AI processing

**Context.** Product rule: data stays in India unless an exception is explicitly approved. Audio and
speech-to-text stay in India [server location to be confirmed]. Only text transcripts (never audio) are sent to an
AI language model provider, after masking. Masking is automated and may miss items, for example names not on the
list, misspelled names, or numbers spoken as words. Staff names are not masked by default. The provider is not yet
chosen; we are comparing providers on India-region availability, data retention, whether they train on customer
data, and whether a data processing agreement is available. Some candidates may process data outside India. Some
providers may keep text temporarily (for example for caching or abuse monitoring). The AI call tracing tool stores
AI inputs and outputs [hosting region to be confirmed].

- **E1.** May masked transcripts be sent to an AI provider that processes them outside India? If so, on what
  conditions? Are there countries to which transfer is restricted, and how should we check this over time?
- **E2.** Is a masked transcript still personal data (it still contains what staff and students said, and staff
  names)? Would masking staff names too change your view?
- **E3.** If processing outside India is used, what must the parent and staff forms say? Is a separate consent
  needed?
- **E4.** What terms should we require from the AI provider: no training on our data, retention limits, deletion,
  processing location, its own sub-providers, breach notice, anything else?
- **E5.** Does temporary retention by the provider (caching, abuse monitoring) need to be handled or disclosed?
- **E6.** For children's data in particular, would you advise using only an India-region AI option even if it
  costs more?
- **E7.** Do the same questions apply to the supporting services (error monitoring, AI call tracing, email) if
  any of them is hosted outside India?

#### F. Staff consent and use for appraisal

**Context.** Teachers, front-desk staff and possibly counsellors are recorded and receive rubric-based feedback.
Scores are produced mainly by automated analysis. A person reviews a report when the staff member disputes a
score or when the software flags a recording; not every report is reviewed by a person. If a dispute is accepted,
the human score is shown and the original automated score stays in the history. Administrators can see some
"Internal" measures that staff do not see. Whether reports will be used for appraisal is not decided.

- **F1.** For staff, is consent the right basis for this processing, or is another basis available in an
  employment setting? If consent, how do we make sure it is freely given, given the employer-employee
  relationship?
- **F2.** Can a school make recording a condition of the job? What should happen if a staff member says No or
  withdraws?
- **F3.** If reports are used for appraisal, pay, promotion or discipline, what extra notice, consent or
  safeguards would you advise? Is there concern about decisions based mainly on automated analysis? Should a
  person review every score that is used in such a decision?
- **F4.** Is the dispute process an adequate way for staff to correct their data? Is it acceptable to keep the
  original automated score in history after a dispute is accepted?
- **F5.** Should staff be able to see the "Internal" measures that administrators see about them?
- **F6.** Should staff always be told in advance when they are being recorded?
- **F7.** Are there other laws or rules (employment law, service rules for school staff, employment contracts)
  that we should check?

#### G. Call recording notice

**Context.** A short spoken notice plays before an incoming reception call connects (see
`call-recording-notice.md`). Callers include parents, prospective parents, vendors and sometimes students. The
analysis is about the receptionist. The caller is not scored, but the call is given a category (for example
complaint, information or fee query) and the caller's share of talk time is measured. [Whether caller phone
numbers or other call details are imported with the recording is to be confirmed.] Consent in Sabha is recorded
per call line, not per call; there is currently no per-call "caller objected" marker.

- **G1.** Is a spoken notice before the call connects adequate for callers, or is their consent needed? If
  consent, does continuing the call after the notice count?
- **G2.** Must the notice mention automated or AI analysis, Schoollog, how long recordings are kept, or where to
  find a fuller privacy notice? Is the shorter variant (about 7 seconds) enough?
- **G3.** Which of the options for callers who object (listed in the call notice draft) are acceptable?
- **G4.** What should happen when the caller is a child?
- **G5.** For outgoing calls made by reception, is it enough for the receptionist to read the short notice at the
  start?
- **G6.** Are there telecom rules, or terms of the school's phone provider, about call recording that we should
  check?
- **G7.** Should call recordings and transcripts have a different retention period from lesson recordings?

#### H. Grievance redressal and breach notification

**Context.** The forms name a grievance officer [at the school] and a Schoollog contact. Sabha logs every playback,
export and score change. Schoollog monitors the system and will have an incident runbook [to be written].

- **H1.** Who should be the grievance contact named in the forms: the school, Schoollog, or both? Are there
  requirements for that person (for example being based in India)?
- **H2.** What response time should we commit to for grievances and requests?
- **H3.** Does the school or Schoollog need to appoint a data protection officer?
- **H4.** If there is a data breach, who must notify the Data Protection Board and the affected people, how fast,
  and with what content? What should the contract require Schoollog to tell the school, and by when?
- **H5.** Because students are not identified, a breach of lesson recordings could not be linked to specific
  students. Should we plan to notify all parents of every affected class?
- **H6.** What records of grievances, requests and breaches should be kept, and for how long?

#### I. Withdrawal of consent and erasure requests, including backups

**Context.** The erasure function deletes audio, intermediate files, transcripts, analyses, scores and disputes
for a recording, a staff member or a whole school, and keeps a minimal record that the erasure happened. Because
students are never identified, we cannot erase one student's voice from a lesson; a parent's withdrawal can only be
handled at class level (stop recording that class, and possibly delete that class's existing recordings). Erased
data remains in backups until they expire [period to be confirmed]. Text already sent to the AI provider is subject
to the provider's own retention. Dispute outcomes are also stored as calibration data for checking scoring
accuracy.

- **I1.** How quickly should withdrawal and erasure requests be acted on?
- **I2.** When a parent withdraws, is it acceptable that we cannot remove one child's voice? Which of the options
  in section 8 of the parent form is acceptable: (a) delete that class's earlier recordings on request, or (b) let
  them expire on the normal schedule?
- **I3.** Does withdrawal require deleting reports already produced from earlier recordings, or only stopping new
  processing?
- **I4.** Is deletion from live systems, with backups expiring after [N] days, acceptable? Must this be stated in
  the forms?
- **I5.** Is it acceptable to keep a minimal record of each erasure (what, when, by whom) and the access log?
- **I6.** Must data derived from erased records (for example calibration records from disputes, or aggregate
  quality figures) also be erased?
- **I7.** If a staff member asks for erasure but the school wants to keep records (for example if reports are used
  in appraisal), how should that be handled?
- **I8.** How should the identity of a person making a request be checked?

#### J. Use of recordings to check quality

**Context.** To measure how accurate transcripts and scores are, Schoollog plans for human annotators to
transcribe and label speakers on a sample of recordings, and for human raters to score a sample against the rubric.
A fixed evaluation set of recordings and transcripts is kept unchanged so later versions of the software can be
compared against it, which may mean keeping some recordings longer than 90 days. Some recordings made before the
pilot may also be used. Annotators are asked to anonymise names in the transcripts they type. [Whether annotators
and raters are Schoollog employees or contractors, and where the annotation tool is hosted, is to be confirmed.]

- **J1.** Is quality checking a separate purpose that must be stated in the parent and staff forms (see the
  optional clause in the parent form, section 5)? Does it need its own consent?
- **J2.** Can recordings in the evaluation set be kept longer than 90 days? If so, for how long, and with what
  wording?
- **J3.** What agreements do annotators and raters need (confidentiality, data handling, location)?
- **J4.** What consent is needed for recordings made before the pilot, and would these drafts cover them?

#### K. The enclosed drafts

- **K1.** Please review the three drafts and tell us what is missing, wrong or unclear.
- **K2.** Which documents need a signature, and which can be a notice only?
- **K3.** Do we also need a privacy notice in the Sabha app or on the school's website?
- **K4.** If a form changes after consent has been collected, must consent be collected again?

<a id="doc-docs-legal-drafts-staff-consent-and-notice-md"></a>

## Staff notice and consent: recording and feedback for teachers, counsellors and front-desk staff

*Source: [`docs/legal/drafts/staff-consent-and-notice.md`](legal/drafts/staff-consent-and-notice.md)*

**DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE**


| | |
| --- | --- |
| Status | Draft v0.1 for legal review (plan task P8.1). Not for use with staff until approved. |
| Date | 14 October 2026 |
| Prepared by | Sabha product team, Schoollog [legal entity name] |
| For review by | [Lawyer name / firm] |
| Language | English only for now. A Hindi version can be added after legal review; it must then be checked by a native Hindi speaker as well as by the lawyer. |

**Notes for reviewers (remove before use):**

- Text in [square brackets] is a placeholder or a decision for the school or the lawyer.
- Lines marked "Drafting note" are for reviewers and are not part of the notice.
- References such as "Q-F" point to the matching section of `questions-for-lawyer.md`.
- The question of whether reports are used for appraisal is deliberately left open (section 7).

---

#### 1. Who this notice is for

This notice is for staff of [School name] whose work conversations may be recorded and analysed using Sabha, a
software service that Schoollog [legal entity name] provides to the school. It explains what is recorded, why,
how your feedback report is produced, who can see it, how long it is kept, and what you can do.

We are asking for your consent under India's Digital Personal Data Protection Act, 2023. Please read the whole
notice before you decide.

#### 2. What is recorded

| Role | What may be recorded |
| --- | --- |
| Teachers | The sound (audio) of selected lessons, recorded on a phone or microphone kept near you. No video. Students' voices may be captured incidentally; students are not analysed (see section 3). Which lessons and how often: [School to fill in]. Who starts the recording: [School to decide, e.g. the teacher records their own lessons]. |
| Front-desk and reception staff | Phone calls on [school reception line(s)], recorded by [the school's phone system, to be confirmed]. [Incoming calls only / incoming and outgoing calls; School to decide.] Callers hear a recording notice before the call connects (see `call-recording-notice.md`). |
| Counsellors | [School to specify which conversations, if any, are recorded, e.g. admission enquiries with parents.] Student counselling sessions are not part of the pilot and must not be recorded without a separate legal review. |

What is not recorded: [School to list, e.g. staff room conversations, staff meetings, personal phone calls,
breaks].

[School to decide, see Q-F: will staff always know in advance when they are being recorded?]

#### 3. Why we record

- **Purpose:** to give you feedback on your teaching or service, and to support your professional development.
- **Students are not analysed.** No student receives a score, profile or rating. The software does not try to
  identify which student is speaking; it labels speakers only by role (for example "Teacher" and "Student(s)",
  or "Receptionist" and "Caller").
- **Callers are not scored.** For reception calls, the analysis is about the staff member's handling of the
  call. The call is also given a category (for example complaint, information or fee query).
- Use of reports for appraisal or other employment decisions: see section 7. This is not yet decided.

#### 4. How your feedback report is produced

Your report is produced mainly by automated analysis. People review it in the cases described below.

1. **Speech to text.** The software turns the recording into a written transcript and labels who spoke when, by
   role.
2. **Measured numbers.** Some figures are calculated directly by the software from the transcript and the
   timing, not judged by AI. For lessons, for example: how much of the time the teacher talks compared with
   students, how many questions are asked, speaking pace, silences, and the longest stretch of uninterrupted
   teacher talk. For calls, for example: call length, hold or silent gaps, and how much the caller talks.
3. **Masking before AI.** Before the transcript is sent to an AI language model, software masks phone numbers,
   ID numbers that look like Aadhaar or PAN, email addresses and students' names. Staff names are not masked by
   default [School to decide whether staff names should also be masked]. The AI model receives text only, never
   audio.
4. **AI judgement against a rubric.** The AI model rates your work on each part of a fixed rubric (a list of
   criteria with descriptions of each level), agreed with [the school's academic head / school]. Every comment
   the AI makes must quote the transcript with a timestamp, so you can see the evidence.
5. **Automatic evidence check.** The software checks that each quote really appears in the transcript. A
   judgement whose evidence cannot be confirmed is not shown.
6. **Human review.** A person at the school ([reviewer role, e.g. academic head or front-desk manager]) reviews a
   report when you dispute a score (section 5) or when the software flags a recording for review, for example
   when it is unsure who was speaking. [School to decide whether a person also reviews every report before it is
   used for anything other than your own development. See Q-F.]

Automated analysis can make mistakes, for example in noisy rooms or with mixed Hindi and English speech. That is
one reason you can dispute any score.

Some newer measures that have not yet passed Schoollog's quality checks may be shown only to school
administrators, marked "Internal". [School and lawyer to decide whether these should be shown to you, hidden from
administrators too, or switched off. See Q-F.]

> Drafting note: describe the system as it actually runs at go-live. Schoollog to confirm each step above before
> this notice is final. No accuracy figures are given here on purpose; any figure added later must come from
> evaluation on real, human-checked recordings.

#### 5. Disputing a score

- You can dispute any score in your report from the report page: choose the item, propose a score and add a
  comment.
- A reviewer ([role]) looks at the evidence and accepts or rejects your dispute, with a note. You are told the
  outcome.
- If your dispute is accepted, the reviewer's score is shown in your report, marked as a human score. The
  original automated score is kept in the report's history.
- Dispute outcomes are also used to check and improve how accurately the software scores.
- Disputing a score will not be held against you. [School to confirm.]

#### 6. Who can see your recordings and reports

| Who | What they can see |
| --- | --- |
| You | Your own recordings, transcripts and reports. You cannot see colleagues' reports, and they cannot see yours. |
| Your reviewer or manager: [School to list roles, e.g. academic head, coordinator, front-desk manager] | Recordings and reports for the staff in their section or unit. |
| School administrators: [School to list roles, e.g. principal, management] | All recordings and reports for the school, the school's settings and the access log. |
| Schoollog [legal entity name], as service provider | Only staff Schoollog has authorised, and only when needed to run or fix the service. [Schoollog to confirm.] |
| AI language model provider: [name, to be confirmed] | Masked transcript text only (see section 4), not audio. |
| [OPTIONAL, see Q-J: trained reviewers working for Schoollog] | [A sample of recordings, to check that transcripts and scores are accurate.] |

Every time someone plays a recording, exports a report or changes a score, the software logs who did it and
when.

#### 7. Use for appraisal

> **[QUESTION FOR THE SCHOOL AND THE LAWYER: NOT DECIDED. Do not finalise this notice until it is answered.]**
>
> Will recordings, scores or reports be used in performance appraisal, pay, promotion, confirmation of
> employment or disciplinary decisions?
>
> Options to consider:
>
> - (a) No. Used only for development feedback. The notice would say so plainly.
> - (b) Yes, with safeguards. The notice would say exactly how they are used, which safeguards apply (for example
>   a person reviews every score used, and the staff member can dispute it first), and whether a separate consent
>   is asked for.
> - (c) [Other, to be specified.]
>
> See Q-F.

#### 8. Where your data is stored

Recordings, transcripts and reports are stored on servers in India, in the Mumbai region of Amazon Web Services
(AWS, region "ap-south-1"). [Schoollog to confirm the complete list of storage and processing locations, including
the speech-to-text servers and the database.]

[If the AI language model processes the masked text outside India, this must be stated here, with the country.
See Q-E.]

#### 9. How long we keep it

| Data | Kept for |
| --- | --- |
| Audio recordings | Deleted automatically after 90 days [School to confirm, or set a shorter period]. |
| Transcripts, scores and reports | [Period, to be decided by the school and the lawyer.] |
| Disputes and reviewer notes | [Period, to be decided.] |
| Access log (who played, exported or changed what) | [Period, to be decided.] |
| Backup copies | [Period, Schoollog to confirm.] |

When data is erased on request, the software keeps a minimal record that the erasure took place (what was
erased, when and by whom), but not the erased content.

#### 10. Your choices and requests

- **Your choice.** [Lawyer and school to confirm, see Q-F: declining or withdrawing consent will have no adverse
  effect on your employment.]
- **See your data.** You can see your own reports and transcripts in Sabha at any time. To ask for a copy or for
  more information, contact the grievance officer (section 11).
- **Correct your data.** To challenge a score, use the dispute option (section 5). To report a mistake in a
  transcript, [process to be defined].
- **Withdraw consent.** You can withdraw your consent at any time, as easily as you gave it, by [method, e.g.
  writing to the grievance officer or HR]. After that, [School to describe, e.g. no new recordings of your work
  will be made or processed] within [N working days]. For recordings already made: [School and lawyer to decide:
  (a) deleted on request, or (b) kept until the normal deletion dates in section 9].
- **Ask for erasure.** You can ask for your recordings, transcripts, scores and reports to be erased. [Lawyer to
  confirm any limits, for example where the school must keep records for another reason.]
- **Complaints.** You can complain to the grievance officer. If you are not satisfied with the reply, you can
  [escalation route; lawyer to confirm, e.g. complain to the Data Protection Board of India].

#### 11. Contact

- Grievance officer: [Name], [Email], [Phone], [Office hours].
- HR or staff contact at the school: [Name, email].
- School: [School name], [Address].
- Service provider: Schoollog [legal entity name], [Address], [Contact email].
- We will reply within [N days; lawyer to confirm].

#### 12. Acknowledgement and consent

Name: ______________________

Role: ☐ Teacher ☐ Counsellor ☐ Front-desk / reception ☐ Other: ____________

Staff ID [optional]: ____________

☐ I have read this notice, or it has been explained to me, and I have had the chance to ask questions.

Please tick one:

☐ **Yes**, I agree to my [lessons / calls / conversations listed in section 2] being recorded and analysed as
described in this notice.

☐ **No**, I do not agree.

[If reports are used for appraisal (section 7): a separate tick box may be needed. Lawyer to advise.]

Date: ____________ Signature: ______________________

**For school use only:** Received by (name and role): ______________ Date: ________
Consent reference number: ______________

> Drafting note: the consent reference number links this form to the consent record in Sabha. Sabha is designed
> so that a recording is not processed unless it is covered by a valid consent record for that staff member (or,
> for calls, that call line).

<a id="part-10"></a>

# Part 10. Appendix: the 8-week plan (history, kept as written)

<a id="doc-docs-prompts-readme-md"></a>

## Claude Code prompts for Sabha

*Source: [`docs/prompts/README.md`](prompts/README.md)*

One prompt per task in the 8-week execution plan. Prompt IDs match the plan's sub-problem IDs
(for example `P2.4` builds sub-problem 2.4), so your tracker, the plan and these prompts line up.

### Setup (once)

1. Copy this kit into the root of the `sabha` repo: `CLAUDE.md`, `.claude/commands/`, `docs/`.
2. Open the repo in VS Code and start Claude Code. It reads `CLAUDE.md` automatically every session.
3. Custom commands now available: `/review`, `/tenant-check`, `/gate-check 1|2|3`, `/fix <description>`.

### How to run each prompt

1. Start a **fresh Claude Code session per prompt** (or `/clear`), so context stays small and on-task.
2. Switch to **plan mode** (Shift+Tab) and paste the prompt. Read the plan; correct it before any code is written.
3. Approve, let it implement, then run `make test` and `make lint` yourself.
4. Run `/review` on the diff. Fix FAILs before committing.
5. Commit with the prompt ID in the message: `P2.4: celery queues per stage with DLQ`.
6. Tick the matching sub-problem in the execution plan.

### Order and files

Only work that is not finished is listed (updated 2026-10-27). Tasks marked "partly built" carry a status note under
their heading saying what exists and what remains; some of those notes are older than the commits that followed, so
check `git log` too. Removed prompts are in git history.

Since 2026-10-24 the order is **product first**: more conversation types and the coaching loop in weeks 2–7, and all
infrastructure (AWS, Auth0, deploy, CI/CD, monitoring) together in week 8.

**1. Product (now)**

| Task | File | What remains |
| --- | --- | --- |
| P6.8 role views (partly built) | `week-6.md` | Rubric editing and publishing (needs P5.9 calibration and real rater scores), the plans and billing page (needs a billing system); keyboard focus order is checked only by axe so far |
| P6.2 app shell (partly built) | `week-1.md` | Tenant switcher (when a person belongs to several organisations), Playwright smoke test |
| P2.7 notifications (partly built) | `week-5.md` | Webhook settings and the delivery task (signing is built); emails are done |
| P7.2 limits and quotas (partly built) | `week-5.md` | Limiter in the auth dependency, lane by duration, admission ETA, the 80 % warning email (quota checks on upload are done) |
| P7.3 backups, retention, erasure (partly built) | `week-6.md` | Week 8: Atlas continuous backup, bucket lifecycle for exports, the restore drill on staging |
| P7.8 admin ops (partly built), P8.6 usage export | `week-7.md` | Pause/resume per tenant, demo seed data, usage export for invoicing (retry, close and processing details are done) |

**2. Quality (needs real, annotated recordings)**

| Task | File | What remains |
| --- | --- | --- |
| P5.3 model bake-off | `week-3.md` | Not started |
| P5.9 calibration, P4.7 CI eval gate | `week-6.md` | Not started; tools from P4.2–P4.6 are built |
| P3.4b diarization finish | `week-3.md` | NeMo Sortformer and the GPU image, once a GPU exists |
| Gates 1–3 | `week-3.md`, `week-6.md`, `week-7.md` | Reviews against real numbers |

**3. Last week (infrastructure and go-live)**

| Task | File | What remains |
| --- | --- | --- |
| P1.3 staging Compose and Terraform | `week-1.md` | Not started |
| Auth0 tenant | `docs/setup/auth.md` | Code is built; the tenant replaces the local dev sign-in |
| P7.1 monitoring (partly built) | `week-2.md` | Trace propagation through Celery, Prometheus, Grafana, Sentry |
| P7.5 load and chaos, P7.6 security (started), P7.7 production and alerts | `week-7.md` | See each prompt |
| P8.4 onboarding pack | `week-7.md` | Not started |
| P8.8 go-live, P8.9 health report, P8.7 feedback log | `week-8.md` | Not started |

#### Removed because they are done (or dropped)

| Task | Follow-up still open |
| --- | --- |
| P0.2 dev setup and design spike, P0.5 env template, P0.8 rubric v0.1 drafts, P4.1 annotation tool, P1.1 monorepo, P1.4 API skeleton, P6.1 design system, P8.3 recording guide, P5.4 rubric schema, P5.5 computed metrics, P4.4 rater kit | None |
| P0.6 LLM provider | OpenAI `gpt-6-luna` since 2026-10-24 (o3-mini was shut down); data residency terms and settings to confirm with OpenAI (`docs/llm-providers.md`) |
| P0.7 LIS baselines | Dropped: there is no LIS codebase. ASR providers are compared on our own gold set instead |
| P8.1 consent drafts | With the lawyer; sign-off is a people task (plan 8.5) |
| P1.2 CI | Dropped 2026-11-02: GitHub Actions removed at the product owner's request (ADR 0010); checks run locally |
| P1.5 identity and roles (Auth0 sign-in, invites, `GET /v1/me`, `scripts/admin/create_tenant.py`) | "Done when" (log in with Google on dev) needs the Auth0 dev tenant (`docs/setup/auth.md`) |
| P2.3 state machine and stage runs (`transition()`, `stage_runs`) | Its "Done when" (the complete endpoint uses `transition()`) is met |
| P2.1 create recording and presigned multipart upload (`POST /v1/recordings`, `/parts`, `sabha_core/storage.py`) | "Done when" (a script uploads 500 MB part by part) is shown at small scale in tests; the full-size run needs P2.2's complete endpoint and staging |
| P2.2 complete upload, checksum and duplicates (`POST /v1/recordings/{id}/complete`, `upload_cleanup.py`) | The outbox event is written in P2.5 (TODO in `services/recordings.py`); P2.4 schedules the stale-upload cleanup |
| P5.1 LLM gateway (`sabha_llm.gateway`, OpenAI Responses adapter, budgets, `llm_calls`, `sabha_analytics.judge`) | Tracing is OpenTelemetry; a Langfuse adapter waits for a self-hosted instance in India. "Done when" on real calls needs an OpenAI key (test data only until the residency sign-off) and confirming `o3-mini` is still available to the project |
| P2.4 Celery queues, retries and dead-letter queue (`celery_app.py`, `tasks.py`, `stages/runner.py`, `maintenance.py`, `make workers` / `beat` / `relay`) | Prometheus metrics move to P7.1; containerised worker, beat and relay services to P1.3's staging Compose; routing short recordings to the priority lanes needs their duration (from P3.2) |
| P2.5 transactional outbox and change-stream relay (`sabha_core/outbox.py`, `relay.py`) | None: completing an upload starts preprocessing (which fails with `stage_not_built` until P3.2) |
| P1.6 tenancy (`sabha_core` models, repo, indexes; `sabha_api.deps.tenant_repo`) | /tenant-check finding 3, email delivery keys without a tenant, is fixed when P2.7 stores its delivery log |
| P3.1 ASR provider layer (Sarvam AI, ADR 0006) | "Done when" needs a valid `SARVAM_API_KEY` (the current one is rejected with 403) and Sarvam's data terms in writing before real audio |
| P4.2 gold-set tooling, P4.3 WER and role eval, P4.6 kappa and grounding eval | Tools built; run them on the real gold set and rater scores once those exist |
| P5.2 PII redaction | Built with regular expressions; CLAUDE.md names Presidio. Decide whether to adopt Presidio |
| P6.5 transcript view, P6.6 report page | None: on real data since P5.7b |
| P3.2 normalise, P3.3 VAD and segment map, P3.4a diarization (CPU), P3.5 speech-to-text, P3.6 roles, P3.7 transcript | Run on more real files once recordings exist; tune `VAD_*`; transcript text search |
| P5.6 scoring and grounding, P5.7 synthesis and storage, P5.7b analysis API, P5.8 reception | A real lesson and 10 real calls end to end on staging |
| P6.3 upload screen, P6.4a/P6.4b overview, P7.4 permission tests | Add every new route to `tests/security/permissions.yaml` (the test enforces it) |
| Sales meetings (rubric `sales.company.v0.3`, deal card), meetings (`meeting.company.v0.1`, ADR 0008) | Added 2026-10-24 to 2026-10-26; no prompt file |
| Company reception: walk-in visitors (`reception.company.v0.1`), the ticket on the report with verified quotes | Draft rubric for the owner's review; a full run on audio once Sarvam has credit |
| P6.7 disputes: raise, the Disputes tab in Reviews, decide, email; the reviewer's score counts in the overall and trends | Calibration records are stored on each dispute; reading them into the calibration loop is P5.9 |
| P2.8 re-analysis: one recording or many (count first, 100 per request), every version kept, numbers from the latest only | Re-analysis with a chosen rubric version is in the API only (the app always uses the current rubric) |
| P2.6 live status: GET /v1/events and pages that update themselves, polling only as a fallback | Remaining from the prompt: none |
| P1.7 settings: `GET`/`PATCH /v1/settings` and the Settings page (words, types within the plan, audited); new workspaces by `scripts/admin/create_tenant.py` (owner's choice, 2026-10-27, no self-sign-up) | None |
| P6.8 role views: read-only rubric pages for everyone, role-only pages guarded, not-found and session-ended states, pages loaded on first open (main bundle 548 to 396 kB), axe and contrast checks, browser tests per role (`e2e/roles.e2e.ts`) | "Internal" admin-only scores are left out: golden rule 5 (owner, 2026-10-27) |
| P6.2 menu numbers: recordings per type (`GET /v1/recordings/counts`), the plan block (`GET /v1/usage`), the test against hard-coded nouns | Allowances: Starter 100 h (uploads pause), Growth 500 h (extra billed), pilot none (owner, 2026-10-27, from the plans design); `scripts/admin/set_plan.py` overrides one customer's. Hours count once transcription succeeds |
| P6.9 consent (partly built) | Parked for the owner's law team (2026-10-26); golden rule 9 stays enforced at upload |

### Coverage check

Every engineering sub-problem in the plan (59 of 67) has a prompt. The 8 remaining sub-problems need people,
not code: 0.1 approval, 0.3 pilot schools, 0.4 recordings, 4.2 gold transcripts (people correct; P4.2 builds
the tooling), 4.5 rater scoring (P4.4 builds the kit), 8.1 and 8.2 legal documents (P8.1 drafts for the
lawyer only), 8.5 legal sign-off. Extra prompts cover gaps the plan implied but did not list as separate
items: notifications (P2.7), re-analysis (P2.8), consent UI (P6.9), admin operations (P7.8), daily health
report (P8.9).

### Prompt-writing tips when you add your own

- Name the files to read first, the exact output, and the test that proves it works.
- State what is out of scope, so Claude Code does not wander.
- Paste error output and logs verbatim instead of describing them.
- For anything touching data access, auth, money or quality numbers, ask for tests first.

<a id="doc-docs-prompts-library-md"></a>

## Everyday prompt library

*Source: [`docs/prompts/library.md`](prompts/library.md)*

Reusable prompts for any week. Paste, then fill the angle brackets.

### Start of day
```text
Read CLAUDE.md, git log for the last 2 days, and docs/prompts/week-<n>.md. Tell me which prompts from this
week are done (based on code and tests present), which are in progress, and what to do next. Do not write code.
```

### Before starting a prompt
```text
Before planning <prompt id>, list the files you need to read, the existing code you will reuse, and any
conflict with CLAUDE.md or earlier decisions in docs/adr/. Ask me anything ambiguous.
```

### Write tests first
```text
For <feature>, write only the tests first: unit tests for the logic and an integration test against
testcontainers. Make them fail for the right reason. Show me before implementing.
```

### Code review of your own change
```text
/review <area or prompt id>
```

### Understand unfamiliar code
```text
Explain <file or module> as if I will maintain it alone: what it does, the data it reads and writes, the
failure modes, and the 3 places a bug is most likely. Point to file:line.
```

### Refactor safely
```text
Refactor <target> for <reason>. Keep behaviour identical: run the full test suite before and after, no public
API changes, and show the diff in small steps.
```

### Performance problem
```text
<endpoint or task> is slow (<numbers>). Profile it (py-spy or cProfile for Python, explain() for MongoDB
queries), show the top 3 costs with evidence, and propose fixes ranked by impact and risk. No changes yet.
```

### Database query or index
```text
Write the MongoDB query/aggregation for <need>, tenant-scoped through the repo, with the index it needs added
to indexes.py. Show explain() output on test data and a test proving tenant isolation.
```

### UI from the design
```text
Build <component/page> matching docs/design/<file>.png and docs/design/source/<file>.dc.html, using only the
components in apps/web/src/design and labels from useLabels(). List any visual differences you could not match.
```

### Write an ADR
```text
Write docs/adr/<NNNN>-<title>.md for the decision <decision>: context, options considered, decision,
consequences, how to revisit. Under 1 page.
```

### End of day
```text
Summarise today's changes from git diff/log into docs/changelog.md (date, prompt ids, what changed, what is
left), and list tomorrow's first task.
```

### When Claude Code is going in circles
```text
Stop. Summarise what you tried, what failed and the exact error. Propose 2 different approaches with trade-offs.
Wait for me to choose.
```

<a id="doc-docs-prompts-week-1-md"></a>

## Week 1 — Foundations and upload

*Source: [`docs/prompts/week-1.md`](prompts/week-1.md)*

Goal: a logged-in user uploads a large file directly to storage and sees status `UPLOADED`.

---

### P1.3 · Staging with Docker Compose and Terraform

Plan task 1.3. Read first: `docs/setup/cloud-checklist.md`, `.env.example`.

```text
Create staging infrastructure as code. I will run terraform apply myself after reviewing the plan.

1. infra/terraform/ (AWS ap-south-1): S3 buckets (audio, artefacts, backups) with block public access,
   SSE-KMS encryption, versioning on backups, lifecycle (audio to infrequent access after 30 days, expiry
   configurable per prefix), CORS for presigned browser uploads from our web origin only; a KMS key; an IAM
   role/user for the app with least privilege; 2 EC2 VMs (app VM CPU, GPU VM g6 with L4, or a variable to
   point at our existing on-prem L4 host instead); security groups allowing only 443 publicly; outputs.
2. infra/docker-compose.staging.yml: api, workers-cpu, workers-gpu (with NVIDIA runtime), relay, web, caddy
   (automatic HTTPS), and an otel-collector; MongoDB is Atlas (no local mongo) and Redis runs on the app VM.
3. infra/README.md: how to deploy to staging (pull images by SHA, docker compose up -d, migrations, rollback).
4. scripts/deploy_staging.sh that deploys a given image SHA over SSH and runs a health check.

No secrets in files; read them from the VM's .env written by me.
```

Done when: staging is reachable over HTTPS and `/health` responds.

---

### P6.2 · App shell, login and navigation

> **Status (2026-10-22).** Built: React Router + TanStack Query app shell (`src/app`), sidebar in the tenant's words from /v1/me, problem+json toasts with request id, 401 signs out, protected routes, and the local dev sign-in page (VITE_AUTH_MODE=dev; Auth0 last). Recordings list and report page on the real API. Remaining: tenant switcher, nav counts, plan usage block, the lint rule against hard-coded nouns, Playwright smoke test.

Plan task 6.2. Read first: `docs/design/01-overview.png` (sidebar), P1.5 output.

```text
Build the app shell in apps/web using the design components.

- React Router routes: /login, /, /recordings, /recordings/:id, /upload, /reviews, /people, /rubrics,
  /settings; everything except /login is protected.
- Sidebar exactly like the design: logo, tenant switcher (single tenant for now), nav with counts, conversation
  types list (from tenant enabled_types), plan usage block (static placeholder for now), user block.
- All visible nouns come from the labels returned by GET /v1/me (person, recording, unit); write a useLabels()
  hook and a lint rule or test that fails on hard-coded "Teacher"/"Lesson" in components.
- TanStack Query client with auth header injection and problem+json error handling (toast with request_id).
- Responsive: sidebar stacks above content on phones.

Tests: protected route redirects; labels render from /v1/me; Playwright smoke test logs in (mock OIDC in dev).
```

Done when: you log in on staging and see the shell with your tenant's labels.

<a id="doc-docs-prompts-week-2-md"></a>

## Week 2 — Orchestration and the first half of the audio pipeline

*Source: [`docs/prompts/week-2.md`](prompts/week-2.md)*

Goal: an upload flows automatically through cleaning and speaker detection, and the dashboard shows it live.

---

### P2.6 · Live status over Server-Sent Events

Plan task 2.6.

```text
Add GET /v1/events (SSE). Authenticated; subscribes to Redis channel events:{tenant_id}; filters events
to what the caller may see (staff: only their own person_id's recordings); sends heartbeats every 15 s;
supports Last-Event-ID by replaying the last 5 minutes from the outbox.
Web: a useLiveEvents() hook that updates TanStack Query caches for recording lists and detail; reconnects
with backoff; falls back to polling every 5 s if SSE fails.
Tests: a staff user does not receive another person's events; reconnect replays missed events.
```

Done when: the recordings list updates without a refresh as a job moves.

---

### P1.7 · Organisation profiles and label dictionary

> **Status (2026-10-17).** Already built: profile defaults for school, college and company (sabha_core/profiles.py) and `Tenant.from_profile` (P1.6). Remaining: `POST /v1/admin/tenants`, `PATCH /v1/settings`, `useLabels()` in the web app, and blocking uploads of disabled types.

Plan task 1.7.

```text
Implement organisation profiles.

- packages/core/sabha_core/profiles.py: defaults for school, college and company: enabled_types,
  labels (person, person_plural, recording, recording_plural, unit, manager), default rubric ids per type,
  consent defaults (school strictest), retention_days.
- POST /v1/admin/tenants (internal admin only) creates a tenant from a profile; PATCH /v1/settings lets an
  owner rename labels and toggle enabled types within plan limits.
- The web app reads labels everywhere via useLabels() (from P6.2).
Tests: each profile yields correct defaults; staff cannot change settings; disabling a type blocks new uploads
of that type but keeps old reports readable.
```

Done when: switching a test tenant to `company` changes the UI words to Sales rep, Call, Team.

---

### P1.8 · Audit log

> **Status (2026-10-19).** Partly built: the `AuditEntry` model, `audit_log` collection with its (tenant_id, at) index, and `sabha_api.audit.audit()` used for `recording.create` (P2.1). Remaining: the other actions as their routes land, `GET /v1/audit` (owner/admin, filters, cursor pagination) and the immutability tests.

Plan task 1.8.

```text
Implement an append-only audit_log: {tenant_id, actor_user_id, actor_role, action, target_type, target_id,
at, ip, user_agent, request_id, meta}. Actions: recording.create, recording.play, recording.download,
transcript.view, analysis.view, score.dispute, score.change, export.create, settings.change, user.invite,
data.erase. Helper audit(...) used by services; no update or delete paths exist. GET /v1/audit (owner/admin,
filters, cursor pagination). Add a TTL-free index on (tenant_id, at). Playback is logged when the API issues
a presigned GET URL for audio.
Tests: every listed action writes an entry; staff cannot read the audit log; audit entries cannot be modified.
```

Done when: opening a recording's audio writes an audit entry visible to an admin.

---

### P3.2 · Validate and normalise audio

> **Status (2026-10-20).** Built: `apps/workers/sabha_workers/stages/preprocess.py`. It writes `normalised.wav`, `playback.opus` and `audio.json`, and records `duration_ms` and `audio` on the recording. Checked on a real 21-minute lecture (mp3 with cover art).

Plan task 3.2.

```text
Implement the preprocess stage (apps/workers/tasks/preprocess.py, queue cpu.preprocess), step 1 of 2.

- Download the original from S3 to a temp dir; ffprobe it; reject (PermanentError, code invalid_audio) corrupt
  files, unsupported codecs, duration < 30 s or > 3 h; store duration, codec, sample rate, channels.
- ffmpeg to 16 kHz mono PCM WAV with EBU R128 loudness normalisation and a high-pass filter (~80 Hz); write
  normalised.wav and a 32 kbps Opus playback copy (playback.opus) to {tenant}/{rec}/preprocess@v1/.
- Never modify the original object.
Tests with small fixture files: mp3, m4a, wav, webm with audio, a video mp4 (audio extracted), a corrupt file,
a too-short file.
```

Done when: any supported fixture produces `normalised.wav` and `playback.opus`.

---

### P3.3 · Voice activity detection and segment map

> **Status (2026-10-20).** Built: `apps/workers/sabha_workers/stages/vad.py` (Silero VAD v6.2.3 through onnxruntime, model pinned by SHA-256 and fetched by `make models`, telemetry forced off: docs/security/findings.md #7). It is step 2 of the preprocess stage and writes `compact.wav` and `segments@v1.json`; a recording with no speech goes to NEEDS_REVIEW (`no_speech`). Every time mapped exactly in both directions on 2 real dev files (a 21-minute lecture and an 18-minute interview). Remaining: 3 more real files for the "done when", and tuning the `VAD_*` settings (unmeasured defaults) on the gold set.

Plan task 3.3. **Tests first** for the time mapping.

```text
Implement preprocess step 2: Silero VAD and the segment map.

- Run Silero VAD on normalised.wav; add 300 ms end padding to each speech region (LIS showed Silero clips
  250–350 ms off utterance ends); merge gaps shorter than 1.5 s; keep params in settings.
- Produce segments@v1.json: [{orig_start_ms, orig_end_ms, compact_start_ms}], plus compact.wav containing
  only speech, and stats {total_ms, speech_ms, silence_ms, longest_silence_ms}.
- sabha_core/timemap.py: compact_to_original(ms) and original_to_compact(ms) with binary search; exact at
  segment boundaries.
- Then transition PREPROCESSING → DIARIZING.

Tests first: mapping round-trips; boundaries; property test with random segment maps; stats add up.
```

Done when: 5 real files have segment maps that round-trip exactly.

---

### P3.4a · Diarization (first pass)

> **Status (2026-10-21).** Built for CPU: `sabha_asr/diarization.py` (pyannote community-1, pinned revision; `ScriptedDiarizer` for tests) and `apps/workers/sabha_workers/stages/diarize.py`, which writes `diarization@v1.json` on both timelines. `make setup-speech` installs pyannote + CPU PyTorch and fetches the model (HF_TOKEN). Measured on this dev machine (CPU, 8 threads): 5 minutes of interview speech took 433 s (1.44x real time), 1.15 GB peak memory at batch size 8, 3 speakers; no network connections (strace). Telemetry off: docs/security/findings.md #7 and #8. Remaining: NeMo Sortformer and the GPU image's CUDA build (Dockerfile.gpu header) once a GPU exists; running on gold-set files.

Plan task 3.4 (continues in week 3).

```text
Implement the diarization stage (apps/workers/tasks/speech.py, queue gpu.speech).

- Behind an interface in sabha_asr/diarization.py with two implementations: pyannote (community model) and
  NVIDIA NeMo Sortformer; one is active via settings. Load the model once per worker process; run on the L4.
- Input compact.wav; output diarization@v1.json: turns [{speaker_label, start_ms, end_ms}] on the COMPACT
  timeline plus the same turns mapped to ORIGINAL time using timemap.
- For teaching recordings, allow many raw speakers; role assignment (P3.6) collapses students later.
- Record GPU time and real-time factor in stage_runs meta.
Tests: interface contract with a fake model; a short fixture with two speakers on GPU-less CI uses the fake.
```

Done when: diarization runs on staging GPU for gold-set files.

---

### P6.3 · Upload screen

> **Status (2026-10-22).** First version built (`src/pages/UploadPage.tsx`, `pages/upload/upload.ts`): one file up to 512 MB, type and person, consent reference, SHA-256, Idempotency-Key, 3 parts in parallel with retries, duplicate confirmation. Remaining: drag-and-drop and several files, hashing in a Web Worker, resume after reload (IndexedDB + POST /parts), plan-hours panel, Playwright network-drop test.

Plan task 6.3. Read first: `docs/design/03-upload.png`, `docs/design/source/Upload.dc.html`.

```text
Build /upload matching docs/design/03-upload.png.

- Drag-and-drop zone + "Choose files"; client-side validation (format, size <= 1 GB, duration read via an
  <audio> element where possible); duplicate check by name+size in the current list.
- Per-file: type select (tenant enabled types), person select, status, progress bar, remove/cancel/resume.
- Upload flow: compute SHA-256 in a Web Worker (streamed), POST /v1/recordings with an Idempotency-Key,
  upload parts in parallel (3 at a time) with retry and resume (persist upload state in IndexedDB so a page
  reload resumes), POST /complete.
- Consent checkbox and plan-hours estimate panel as in the design (consent is enforced server-side in P6.9).
- Accessible: keyboard operable, aria-live status updates.
Tests: Vitest for the upload state machine; Playwright uploading a fixture and simulating a dropped connection.
```

Done when: a 1 GB file survives a network drop and resumes.

---

### P6.4a · Overview shell with live status

Plan task 6.4 (finished in week 5 with real numbers).

```text
Build / (Overview) matching docs/design/01-overview.png: metric strip (placeholders), "Processing now"
counts per stage from GET /v1/recordings/stats (implement it: counts by status for the tenant), recent
recordings table from GET /v1/recordings (cursor pagination, filters by type), live updates via
useLiveEvents(). Leave the "Where coaching helps most" panel as an empty state until week 5.
Tests: table renders statuses with the right chips; live event updates a row.
```

Done when: uploads appear and change status live on the overview.

---

### P7.1 · Monitoring and tracing

> **Status (2026-10-17).** Already built: OpenTelemetry tracing set-up for the API (sabha_core/telemetry.py). Remaining: trace propagation through outbox and Celery, Prometheus metrics, Grafana dashboards, Sentry.

Plan task 7.1.

```text
Set up observability for staging.

- OpenTelemetry: API and workers export traces to the otel-collector; the recording_id is set as a span
  attribute and the trace context is propagated through outbox events and Celery headers, so one trace shows a
  recording's whole journey.
- Prometheus metrics: HTTP latency by route, queue depth and age per queue, stage duration, retries, DLQ size,
  GPU utilisation and memory (DCGM exporter on the GPU VM), LLM tokens and cost (from P5.1 later).
- Grafana dashboards as JSON in infra/grafana/: "Pipeline", "API", "GPU", "LLM cost".
- Sentry for API, workers and web with release = git SHA; scrub PII.
Tests: a smoke test that a span carries recording_id across the API → relay → worker hop.
```

Done when: one recording's full journey is visible as a single trace in staging.

<a id="doc-docs-prompts-week-3-md"></a>

## Week 3 — Speech-to-text, model choices and Gate 1

*Source: [`docs/prompts/week-3.md`](prompts/week-3.md)*

Goal: real pilot lessons become speaker-labelled transcripts, and the speech and language models are chosen
with measured evidence.

---

### P3.4b · Finish diarization

Plan task 3.4.

```text
Finish diarization: evaluate pyannote vs Sortformer on 5 gold-set files using eval/roles.py once it exists
(P4.3) or a quick DER script; pick one via settings; handle overlapping speech (keep overlaps, mark them);
handle 1-speaker recordings gracefully; add GPU memory guards (OOM → TransientError with smaller batch).
Write docs/adr/0003-diarization.md with the measured comparison (no invented numbers; MISSING if not run).
```

Done when: the chosen diarizer runs reliably on all gold files.

---

### P3.5 · Speech-to-text with batching

> **Status (2026-10-22).** Built: `apps/workers/sabha_workers/stages/transcribe.py` writes `asr@v1.json` (compact timeline) and cost inputs in stage-run meta, saving each batch of 10 chunks so a retry resumes. Checked live with synthetic speech through Sarvam (saaras:v4): word-perfect, en-IN, 0.6 s for 12 s. The cross-job GPU batcher is not used with a hosted API. Remaining: real pilot lessons on staging.

Plan task 3.5. Read first: `eval/baselines/lis-baselines.md`.

```text
Implement the transcribe stage (queue gpu.speech) using sabha_asr with the provider chosen from the LIS
baselines (I will tell you which).

- Chunk compact.wav at VAD boundaries into chunks of at most ~30 s (never cut mid-word; overlap 0.5 s and
  de-duplicate words at chunk joins).
- Batch chunks across jobs on the GPU when several are queued (a small in-process batcher with a max wait of
  2 s), concurrency 1 per GPU.
- Output asr@v1.json with words {text, start_ms, end_ms, confidence} on the compact timeline, model id/version,
  RTF, GPU seconds.
- Record cost inputs: GPU seconds per audio second in stage_runs meta (cost is calculated later from these).
Tests: chunk boundaries never split words in a fixture; join de-duplication; batcher respects max wait.
```

Done when: real pilot lessons transcribe on staging with timestamps.

---

### P3.6 · Speaker role assignment

> **Status (2026-10-22).** Built into the transcribe stage (`apps/workers/sabha_workers/stages/transcript.py`): roles from the recording's rubric with the heuristics, the small-LLM tie-breaker when unsure (`stages/roles_llm.py`, through the gateway, so text is redacted), `roles@v1.json`, and NEEDS_REVIEW `unclear_roles` when still unsure (the transcript is kept for the reviewer). Remaining: check role accuracy on gold files (eval/roles.py).

Plan task 3.6.

```text
Implement role assignment (part of the transcribe stage, after ASR).

- Inputs: diarization turns, ASR words, recording type, rubric roles.
- Heuristics: teaching → the speaker with the largest talk share and most long turns = teacher, all others =
  students; reception → first speaker who greets with a school/company name pattern or the one on the
  receptionist channel if stereo = receptionist, other = caller.
- If heuristics disagree or confidence < 0.7, ask the small LLM via sabha_llm (after P5.1; until then mark
  low confidence) with only the first 2 minutes of redacted text; if still unsure → NEEDS_REVIEW with reason
  unclear_roles.
- Output roles@v1.json {speaker_label: role, confidence, method}.
Tests: fixtures for clear teacher, two-adult classroom, reception call; low confidence routes to NEEDS_REVIEW.
```

Done when: roles are correct on most gold files and low-confidence cases are flagged, not guessed.

---

### P3.7 · Transcript assembly

> **Status (2026-10-22).** Built into the transcribe stage: `transcript@v1.json` on the original timeline and a `transcripts` document (roles, language mix, rubric). `GET /v1/recordings/{id}/transcript` is built (P5.7b). Remaining: text search.

Plan task 3.7.

```text
Assemble the canonical transcript (end of the transcribe stage), then transition TRANSCRIBING → ANALYZING.

- Merge ASR words with diarization turns (assign each word to the turn with max overlap), group into
  utterances {role, speaker_label, start_ms, end_ms (ORIGINAL timeline via timemap), text, avg_confidence,
  low_confidence_spans}.
- Punctuation and casing restoration (use the ASR's own if present; otherwise a lightweight model behind a flag).
- Save transcript@v1.json to storage and a transcripts document {recording_id, version, asr_model,
  language_mix, word_count, storage_key}. Index searchable text in Atlas Search (or a text index locally).
- GET /v1/recordings/{id}/transcript returns it (tenant-scoped, audited), with a presigned playback URL for
  playback.opus.
Tests: original-time remap correct across a removed silence; JSON schema validation; tenant isolation.
```

Done when: every processed file has a canonical transcript with original timestamps.

---

### P5.3 · Model bake-off harness

Plan task 5.3.

```text
Build eval/bakeoff.py to compare 3 LLMs on our task.

- Input: 10 real transcripts (from the dev split), rubric teaching.school.v0.x, and the scoring prompt from P5.6
  (use a simple draft prompt now and note it).
- For each model: run scoring 3 times (temperature 0) to check stability; record JSON validity rate, grounding
  pass rate (quotes found), score stability across runs, latency, tokens, cost (from the configured price table).
- If human scores exist for any of these files, report agreement; otherwise write "no human scores yet".
- Output eval/reports/bakeoff-<date>.md with a table and a recommendation section that I complete.
Never invent figures; missing → MISSING.
```

Done when: you record the chosen model in `docs/adr/0004-llm-choice.md`.

---

### Gate 1 review

```text
/gate-check 1
```

Then update the execution plan's Gate 1 checkbox only if every criterion is PASS.

<a id="doc-docs-prompts-week-4-md"></a>

## Week 4 — Scoring engine and the teaching report

*Source: [`docs/prompts/week-4.md`](prompts/week-4.md)*

Goal: a real lesson gets a full report with verified, playable quotes.

---

### P5.6 · Scoring calls and the grounding verifier

> **Status (2026-10-17).** Already built: the grounding verifier and scoring logic (sabha_analytics/grounding.py, scoring.py). Remaining: real LLM calls through the P5.1 gateway (OpenAI o3-mini) and wiring into the analyze stage.

Plan task 5.6. **Tests first for the verifier.** Read first: `CLAUDE.md` golden rules 5 and 8.

```text
Implement scoring in sabha_analytics/scoring.py and the verifier in sabha_analytics/grounding.py.

Grounding verifier (tests first):
- normalise text (lowercase, strip punctuation and extra spaces, unify common Hinglish spellings via a small
  map), find the best matching window in the (redacted) transcript with rapidfuzz partial_ratio;
  verified if ratio >= 0.90 AND the matched utterance's time range overlaps the quote's claimed time by any
  amount (allow ±5 s tolerance); return matched utterance ids and the corrected original-timeline times.
- A planted fake quote must fail; a quote with small ASR spelling differences must pass.

Scoring:
- Group dimensions into 2–3 calls; prompt = system rules + rubric (dimension definitions + anchors) +
  transcript with utterance ids and original times + computed metrics as context (not to be re-derived).
- Output JSON schema per dimension: {key, score 1–5, rationale (<= 60 words), evidence: [{quote, utterance_id,
  start_ms}] (at least min_quotes)}. Temperature 0; prompt caching on the stable prefix.
- Verify every quote. If a dimension fails verification, re-ask once for that dimension only with feedback;
  if it fails again mark it verified=false and exclude it from the overall score and from the UI.
- Prompts live in packages/analytics/prompts/*.md, versioned and hashed; the hash is stored with results.
Tests: verifier unit tests; scoring with a fake LLM returning one bad quote → re-ask → excluded.
```

Done when: a planted fake quote never reaches the stored analysis.

---

### P5.7 · Synthesis, schema validation and storage

> **Status (2026-10-22).** Built: `apps/workers/sabha_workers/stages/analyze.py` runs the analysis through the gateway, stores `analysis@v1.json`, an `analyses` document (rubric, model ids, prompt hashes, tokens, cost from llm_calls) and one `scores` document per dimension in one transaction, keyed by (recording, stage version). COMPLETED, or NEEDS_REVIEW with the report's reason. Remaining: a real lesson end to end on staging.

Plan task 5.7.

```text
Complete the analyze stage (queue llm.analyze).

- Synthesis call (mid tier): summary (<= 80 words), strengths (2–3), gaps (2–3), suggestions (exactly 3, each
  referencing a specific moment by utterance id), built ONLY from verified dimension outputs and computed
  metrics. Verify that every suggestion's referenced moment exists.
- Overall score = weighted mean of verified dimensions only, rounded to 1 decimal; if fewer than 60% of weight is
  verified, overall = null and status NEEDS_REVIEW (reason low_verification).
- Validate the final report against a JSON schema; store analyses {recording_id, tenant_id, rubric_id,
  rubric_version, model_ids, prompt_hashes, result, tokens, cost} and flattened scores documents
  {analysis_id, tenant_id, person_id, dimension, score, verified, evidence, created_at}.
- Transition ANALYZING → COMPLETED; the outbox event triggers notify and meter.
Tests: end-to-end with a fake LLM on a fixture transcript produces a valid stored report.
```

Done when: a real lesson on staging reaches COMPLETED with a full report.

---

### P5.7b · Analysis API

> **Status (2026-10-22).** Built: `apps/api/sabha_api/routers/results.py` and `services/results.py`: list (cursor paging), detail, transcript with a presigned playback URL (audited recording.play), latest analysis (audited analysis.view), analysis history and person trends. Visibility: owners/admins all, managers and reviewers their units, staff their own; else 404. Evidence stays redacted for everyone (decided 2026-10-19), so no un-redaction. All routes are in tests/security/permissions.yaml.

Implied by tasks 5.7 and 6.6.

```text
Add endpoints:
- GET /v1/recordings/{id}/analysis → latest analysis with verified dimensions, evidence (un-redacted for
  authorised users only, using the redaction mapping), metrics, summary, suggestions, rubric version, model
  info; 404 if not completed. Audited.
- GET /v1/recordings/{id}/analyses → all versions (for re-analysis history).
- GET /v1/people/{id}/trend?dimension=… → scores over time for a person (manager/admin; staff only self).
Permission rules: staff see only their own; managers their units; counselling restricted (future).
Tests: permission matrix per role; redaction mapping applied only for authorised roles.
```

Done when: the report page can load everything it needs from one call.

<a id="doc-docs-prompts-week-5-md"></a>

## Week 5 — Reception, disputes and fairness

*Source: [`docs/prompts/week-5.md`](prompts/week-5.md)*

Goal: both conversation types work, staff can dispute scores, and one busy school cannot slow the others.

---

### P5.8 · Classify, segment and the reception rubric

> **Status (2026-10-20).** Already built: classify step, phase segmentation, reception ticket and hold-gap metric (sabha_analytics). `rubrics/reception.school.v0.2.yaml` was reviewed, approved as-is and is the pilot version. Escalation handling is "not applicable" on calls with nothing to escalate, and its weight is then shared out over the other dimensions. Ticket categories and statuses are read from the rubric's `output_values`. Remaining: wire classify, segment and the ticket into the analyze stage (after the P3 audio pipeline), then run 10 real calls.

Plan task 5.8. Read first: `rubrics/reception.school.v0.2.yaml`.

```text
Extend the analyze stage.

- Classify step (small tier): if the uploader did not set the type, or set_type_confidence is low, classify
  the conversation type and language mix from the first 3 minutes of redacted text; low confidence →
  NEEDS_REVIEW (reason uncertain_type).
- Segment step (small tier): split into phases from the rubric's phase list (teaching: introduction,
  explanation, guided practice, closing; reception: greeting, need, information, resolution, close) with
  utterance-id boundaries; verify boundaries exist; store for the timeline.
- Use rubrics/reception.school.v0.2.yaml (approved). Reception output adds: category and resolution status from
  the rubric's output_values (category: admission_enquiry, fee_query, transport, general_information, complaint,
  other; status: resolved, follow_up_needed, escalated), follow_up (text + owner role), and a ticket-style summary.
- Reception computed metrics: handle time, hold or silence gaps > 10 s, caller talk share.
Tests: fixture reception call yields a valid report; misclassified-type path goes to NEEDS_REVIEW.
```

Done when: 10 real calls produce ticket-style reports.

---

### P6.7 · Disputes and reviews

> **Status (2026-10-17).** Already built: the dispute dialog and `/reviews` page on mock data (`/dev/reviews`). Remaining: the three endpoints, the `disputes` collection, override scores with history, calibration records, and the resolution notification.

Plan task 6.7.

```text
Backend:
- POST /v1/analyses/{id}/disputes {dimension, proposed_score, comment} — allowed for the person analysed and
  managers; creates a dispute {status open|accepted|rejected, reviewer_id, resolution_note}; audited.
- GET /v1/reviews (reviewers/managers): open disputes and NEEDS_REVIEW recordings for their units.
- POST /v1/disputes/{id}/resolve {decision, final_score?, note}: accepted → store a human override score
  (the AI score stays in history; the UI shows the human score with a marker); every resolution feeds
  rater_scores as calibration data with source "dispute".
Frontend:
- Dispute dialog on the report (dimension, proposed score, comment).
- /reviews page: queue with filters, detail view showing the evidence and transcript, accept/reject with note.
- Notify the person when resolved (uses P2.7).
Tests: permissions; override shown; history kept; calibration record created.
```

Done when: a teacher disputes a score and a reviewer resolves it end to end.

---

### P7.2 · Rate limits, quotas, priority lanes and fair scheduling

> **Status (2026-10-19).** Already built: the fair GPU scheduler and ADR 0005, the Redis token-bucket rate limiter (user buckets keyed by tenant, /tenant-check finding 1 fixed), quota rules, priority-lane queue names, and Celery queues for every lane (P2.4). Remaining: call the limiter from the auth dependency, quota checks in the upload API with the 80% banner, choosing the lane from the recording's duration (from P3.2), the `gpu.speech` dispatcher with the fair scheduler, and the admission-control ETA.

Plan task 7.2.

```text
Implement fairness controls.

- API rate limits: per-tenant and per-user token buckets in Redis (sensible defaults in settings), returning
  429 problem+json with Retry-After only past a hard ceiling; standard rate-limit headers.
- Quotas: monthly audio hours per tenant from plan; warn at 80% (event + banner); at 100% behave per plan
  (pilot/starter: block new uploads with a clear message; growth: allow and meter overage).
- Priority lane: recordings under 10 minutes are routed to high-priority variants of gpu.speech and
  llm.analyze queues.
- Fair scheduling: a per-tenant token scheme in front of gpu.speech so one tenant with a large backlog cannot
  take more than its weighted share while others wait (document the algorithm in docs/adr/0005-fairness.md).
- Admission control: when gpu.speech age exceeds a threshold, the upload API still accepts but returns an
  estimated completion time.
Tests: simulated burst from tenant A does not delay tenant B's short call beyond the target; quota behaviour.
```

Done when: short calls finish within 5 minutes during a bulk upload from another tenant.

---

### P2.7 · Notifications

> **Status (2026-10-19).** Emails are done: the `io.notify` task (`sabha_workers/notifications/notify.py`) emails the person analysed and their unit managers on COMPLETED and admins on FAILED/NEEDS_REVIEW, in each user's language, once per (tenant, delivery key) in the `deliveries` collection, with per-user `report_emails` / `language`; refused emails are recorded and not retried. Remaining: webhooks (tenant endpoint settings, signed delivery task with 24 h retries and its delivery log, SSRF guard) and the "Done when" with a real SES sender.

Implied by the plan's notify stage.

```text
Implement the notify stage (queue io.notify).

- On COMPLETED: email the person analysed (if enabled) and their manager a short "report ready" email with a
  link (no scores or quotes in the email body); on FAILED/NEEDS_REVIEW: email tenant admins with the reason.
- Amazon SES (ap-south-1) adapter; templates in English and Hindi; per-user notification preferences;
  idempotent by (event_id, recipient).
- Webhooks (for later integrations): tenant-configured endpoints receive recording.completed events signed
  with HMAC-SHA256 + timestamp header; retries with backoff for 24 h; a delivery log.
Tests: no duplicate emails on retry; webhook signature verifiable with the documented algorithm.
```

Done when: a completed lesson sends one "report ready" email.

---

### P2.8 · Re-analysis

Implied by the plan's re-analysis endpoint.

```text
Implement POST /v1/recordings/{id}/reanalyze {rubric_version?, reason} (admin/owner): reuses the existing
transcript (no ASR), transitions COMPLETED → ANALYZING, creates a new analyses version, keeps old versions,
and is not billed as new audio hours. Bulk variant for admins: re-analyse all recordings for a rubric version
change, rate-limited. Tests: transcript not recomputed; usage not double-counted; history preserved.
```

Done when: changing a rubric and re-analysing keeps both versions visible.

---

### P6.4b · Overview with real numbers

> **Status (2026-10-17).** Already built: the overview UI, "Where coaching helps most" panel and IST date-range picker on mock data (`/dev/overview`). Remaining: `GET /v1/overview` aggregations through TenantRepo and the nightly weekly summary (`$merge` needs a vetted repository method, see `sabha_core/repo.py`).

Plan task 6.4.

```text
Finish the Overview: metric strip from GET /v1/overview?from&to (recordings analysed, audio hours processed,
silence removed hours, median overall score by type, open disputes) computed with aggregation pipelines
(tenant-scoped); "Where coaching helps most" = lowest median verified dimension scores in the period with
n per item; a date-range picker (IST). Hide any number whose underlying n is 0 rather than showing 0 or a
placeholder. Add a nightly $merge into a weekly per-tenant summary collection for speed.
Tests: aggregation correctness on fixtures; tenant isolation of the aggregation.
```

Done when: the overview shows correct numbers from real pilot data.

<a id="doc-docs-prompts-week-6-md"></a>

## Week 6 — Calibration, Gate 2 and feature freeze

*Source: [`docs/prompts/week-6.md`](prompts/week-6.md)*

Goal: AI scores agree with human raters on the hold-out set, and nothing new is added after Friday.

---

### P5.9 · Calibration loop (train split only)

Plan task 5.9. Read first: `eval/calibration/split.json`, latest `eval/reports/kappa-*.md`.

```text
Help me improve agreement WITHOUT overfitting.

1. Using ONLY the train split, list for each dimension below 0.60: the recordings with the largest AI-human gaps,
   the AI rationale and evidence, the raters' notes.
2. Classify the cause per case: unclear anchor wording, prompt instruction issue, transcript/ASR error,
   role error, genuine rater disagreement.
3. Propose specific changes (anchor wording in the rubric YAML, prompt wording) as a diff — do not apply yet.
4. After I approve, bump rubric/prompt versions, re-run scoring on the train split, then run
   `make eval-kappa` on the HOLDOUT split exactly once for this iteration, and log it in
   eval/reports/calibration-log.md (iteration, changes, train kappa, holdout kappa).
Rules: never look at holdout cases while proposing changes; never change the rubric meaning to match the AI;
stop after 3 iterations and report.
```

Done when: holdout kappa is reported per dimension; dimensions under 0.60 become admin-only.

---

### P4.7 · Evaluation gate in CI

Plan task 4.7.

```text
Add a regression gate.

- eval/regression/: a small fixed set (10 recordings with gold transcripts and rater scores) committed as
  manifests (audio stays in the private bucket; CI fetches with read-only credentials).
- .github/workflows/eval-gate.yml: runs on PRs that touch packages/asr, packages/llm, packages/analytics,
  prompts/ or rubrics/; computes WER, grounding pass rate and kappa on the regression set; fails if any metric
  degrades beyond tolerances in eval/targets.yaml compared with the stored baseline on main.
- Posts a summary table as a PR comment.
- LLM calls in CI use a separate budget and are cached by prompt hash to keep cost low.
```

Done when: a deliberately worse prompt fails the PR.

---

### P7.3 · Backups, retention and erasure

Plan task 7.3.

```text
Implement data lifecycle.

- Backups: Atlas continuous backup enabled (document in runbook); nightly export of critical collections to the
  backups bucket as a second copy; scripts/restore_drill.py restores into a scratch database and verifies counts
  and a sample of documents.
- Retention: a nightly job deletes original audio and playback copies older than tenant.retention_days (default
  90), keeps transcripts and scores; writes an audit entry per batch; dry-run mode.
- Erasure (DPDP): POST /v1/admin/erasure {scope: recording|person|tenant, id} (owner) deletes audio,
  artefacts, transcripts, analyses, scores and disputes for the scope, keeps a minimal tombstone and audit log
  entry; returns a report.
Tests: retention deletes only expired audio; erasure removes every collection and S3 prefix for the scope;
restore drill passes on staging.
```

Done when: a restore is rehearsed on staging and the retention job runs nightly.

---

### P7.4 · Tenant-isolation and permission tests

> **Status (2026-10-19).** Already built: `tests/security/permissions.yaml` (reviewed by the owner) and `test_permission_matrix.py`, which fails if an OpenAPI route is missing from the matrix and calls every route as nine callers (anonymous, owner, admin, managers of the recording's unit and another unit, a reviewer, the uploader, a colleague, another tenant). Presigned upload keys are checked to sit under the caller's tenant (`test_recordings.py`). Remaining: add each new route to the matrix as it lands (the test enforces it), the SSE checks (with P2.6), aggregation checks (with P6.4b), and a final `/tenant-check` run.

Plan task 7.4.

```text
Strengthen security tests in tests/security/.

- Generate tests for EVERY route in the OpenAPI spec: for each role (owner, admin, manager, reviewer, staff)
  and for a user from another tenant, assert the expected status per a permission matrix file
  tests/security/permissions.yaml (write the matrix; I will review it).
- S3: presigned URLs are only issued for keys under the caller's tenant prefix.
- SSE: events never cross tenants or reach staff for other people's recordings.
- Aggregations and search queries include the tenant filter.
Run /tenant-check and fix every finding before finishing.
```

Done when: the full permission matrix passes in CI.

---

### P6.8 · Role-based views and polish

Plan task 6.8.

```text
Frontend role behaviour and polish:
- Staff: see only their own recordings and reports; no overview of others; can dispute.
- Manager/reviewer: their units; reviews queue.
- Admin/owner: everything in the tenant, settings, audit log, admin-only (unverified or below-gate) dimensions
  marked "Internal".
- Empty states, loading skeletons, error states with request id, 404 page, session-expiry handling.
- Accessibility pass: keyboard navigation, focus order, contrast check, aria labels on icon buttons.
- Performance: route-level code splitting; report page interactive in under 2 s on staging.
Tests: Playwright per role verifying what is visible and what is not.
```

Done when: a staff account cannot open a colleague's report.

---

### P6.9 · Consent in the product

> **Status (2026-10-19).** Partly built: golden rule 9 is enforced by `transition()` (no consent_ref, nothing moves past UPLOADED), and the complete endpoint keeps recordings without consent at UPLOADED with `awaiting_consent` and does not start processing (P2.2/P2.5). Remaining: consent records (scope, validity), checking expiry and scope, releasing an awaiting recording when consent is added (write `recording.ready`), the admin UI and the upload selector.

Covers the consent tick in task 6.3 and golden rule 9.

```text
Enforce consent end to end:
- Tenants store consent records: {consent_ref, scope (school-year class/section, staff member, call line),
  valid_from, valid_to, document_url}. Admin UI to add/edit them.
- Upload screen: consent selector (pre-filled for the person/unit when a valid record exists) plus the
  confirmation checkbox; the API rejects processing when consent_ref is missing, expired or out of scope
  (recording stays UPLOADED with awaiting_consent).
- Report and audit show which consent record covered each recording.
Tests: missing/expired consent blocks the pipeline; valid consent proceeds.
```

Done when: no recording can be processed without a valid consent record.

---

### Gate 2 review

```text
/gate-check 2
```

Feature freeze after Friday: from now on only fixes, tests, docs and operations work.

<a id="doc-docs-prompts-week-7-md"></a>

## Week 7 — Hardening and pilot readiness

*Source: [`docs/prompts/week-7.md`](prompts/week-7.md)*

Goal: the system survives a bad day, production is live with alerts, and schools are ready.

---

### P7.5 · Load and chaos tests

Plan task 7.5.

```text
Build infra/loadtest/ with k6 (or Locust if you prefer; say why).

Scenarios against staging (never production):
1. Burst: 300–500 lecture uploads (use 5 real-length test files reused with different ids; consent records for
   a test tenant) over 30 minutes from 3 tenants, plus a steady trickle of 5-minute reception calls.
2. API: 50 concurrent users browsing overview, reports and transcripts.
Measure: upload success rate, p95 upload-to-result for 60-min files and short calls, queue age per queue,
GPU utilisation, error rates, LLM cost per audio hour. Compare with SLOs in docs/slo.md (write it from CLAUDE.md
and the plan: 99.5% API availability, 60-min file p95 <= 30 min, short call p95 <= 5 min, >= 99% job success).

Chaos script (scripts/chaos.sh): kill a CPU worker mid-job, restart the GPU worker, restart Redis, stop the relay
for 2 minutes, drop Mongo primary (Atlas test failover). Verify no lost or duplicated jobs.
Write results to eval/reports/load-<date>.md. Never invent results; if a run is incomplete, say so.
```

Done when: p95 targets are met with zero lost jobs, or the report states exactly what failed.

---

### P7.6 · Security checks

> **Status (2026-10-19).** Started: `docs/security/findings.md` (pip-audit clean; pnpm audit: one high and one moderate, both build-time Tailwind 3 dependencies, accepted with reasons; the three /tenant-check findings fixed). Remaining: the checks listed there under "Not run yet" (ZAP, trivy, bucket policies and IAM, webhook SSRF, ffmpeg protocol whitelist, secrets rotation).

Plan task 7.6.

```text
Run a security pass and fix what it finds.
- Dependency and image scanning (pip-audit, pnpm audit, trivy on our images); fix highs.
- OWASP ZAP baseline scan against staging (authenticated); triage findings in docs/security/zap-<date>.md.
- Review: JWT validation, CORS, security headers, cookie flags, presigned URL scopes and expiry, S3 bucket
  policies, IAM least privilege, rate limits, error messages not leaking internals, logs not containing PII or
  secrets, admin endpoints protected, SSRF in webhook URLs (block private ranges), file-type handling in
  ffmpeg (no arbitrary protocol access: use -protocol_whitelist file).
- Secrets rotation procedure in the runbook.
Output a findings table with severity, status and fix commit.
```

Done when: no high-severity findings remain open.

---

### P7.7 · Production deploy, alerts and runbook

Plan task 7.7.

```text
Prepare production for the pilot.
- infra/docker-compose.prod.yml mirroring staging with prod settings; Terraform workspace for prod;
  separate buckets, KMS key, Atlas cluster and credentials; daily backups verified.
- Deployment: scripts/deploy_prod.sh with a manual approval step, health checks, and one-command rollback to
  the previous image SHA.
- Alerts (Grafana alerting to my phone via a Telegram/WhatsApp/email channel — ask me which): SLO burn rate,
  DLQ growth (> 10 in 1 h), GPU worker down, queue age above threshold, error-rate spike, backup failure,
  certificate expiry, LLM spend above daily budget.
- docs/runbook.md: architecture overview, how to deploy and roll back, how to replay DLQ jobs, how to restore a
  backup, what each alert means and the first 3 steps for it, how to pause a tenant, how to rotate secrets,
  contact list.
```

Done when: a test alert reaches your phone and a rollback has been rehearsed.

---

### P7.8 · Admin operations tools

> **Status (2026-10-19).** Partly built: `scripts/admin/create_tenant.py` creates a tenant and invites its first owner; dead letters are written to `dlq` with replay arguments (P2.4); stage runs carry a heartbeat. Remaining: the admin endpoints and UI, replay, abandon, pause/resume, the recording timeline and `seed_demo.py`. Decide who the cross-tenant "internal admin" is.

Implied by the dead-letter queue and pilot operations.

```text
Build internal admin tooling (owner/internal-admin only, all audited):
- /admin/jobs: DLQ list with error code and context; replay from the last finished stage; mark as abandoned.
- /admin/recordings/{id}: full stage_runs timeline, artefacts list, trace link, cost breakdown.
- /admin/tenants: create a tenant from a profile, set plan and quota, pause/resume processing.
- scripts/seed_demo.py: creates a demo tenant with synthetic (non-real) recordings and reports for training
  sessions, clearly labelled "Demo data".
Tests: replay is idempotent; pause stops new processing for that tenant only.
```

Done when: you can replay a failed job and create a pilot tenant in under 2 minutes.

---

### P8.4 · Pilot onboarding pack

Plan task 8.4.

```text
Create the pilot onboarding pack in docs/pilot/:
- coordinator-training.md: a 45-minute session outline (log in, invite staff, consent records, upload, read a
  report, dispute a score, what the scores mean and do not mean).
- staff-faq.md (English and Hindi): what is recorded, who sees reports, how scores work, how to dispute, privacy.
- quick-start.md with step-by-step screenshots placeholders I will fill from the real app.
- support.md: how pilot users get help (WhatsApp group rules, response times), and how we log issues.
- An in-app "Help" link and first-login welcome checklist for coordinators (small frontend task).
```

Done when: each pilot school has a trained coordinator.

---

### P8.6 · Usage export and manual invoicing

Plan task 8.6.

```text
Implement the billing.meter stage and exports.
- On COMPLETED (first analysis only), write usage_events {tenant_id, recording_id (unique), audio_seconds
  (original duration), type, period (YYYY-MM, IST)}; re-analysis and failed jobs are never billed.
- GET /v1/usage?period=YYYY-MM (owner/admin): totals by type and by unit.
- scripts/invoice_export.py: CSV per tenant per month with included hours, overage hours, and amounts from the
  plan table in config (prices filled by me), plus 18% GST lines; marked "pilot — manual invoice".
Tests: uniqueness prevents double billing; period boundaries in IST.
```

Done when: usage per school for a month exports correctly.

---

### Gate 3 review

```text
Create docs/gate3-checklist.md from the plan's Gate 3 criteria, then run /gate-check 3.
```

Go live only if every item is PASS, including legal sign-off and consent records.

<a id="doc-docs-prompts-week-8-md"></a>

## Week 8 — Pilot go-live and buffer

*Source: [`docs/prompts/week-8.md`](prompts/week-8.md)*

Goal: pilot schools use Sabha on real lessons and calls while we watch closely and fix fast.

---

### P8.8 · Go-live checklist and waves

```text
Create scripts/golive_check.py for a given tenant that verifies, and prints PASS/FAIL:
tenant exists with the school profile, plan and quota set; consent records present and valid for each unit;
coordinator and staff invited; at least one test upload processed end to end on production; alerts firing to
my phone (send a test alert); backup taken today; Sentry receiving events from prod; runbook URL reachable.
Also write docs/pilot/golive-plan.md: wave 1 (1 school, Monday), wave 2 (remaining schools, Wednesday),
rollback criteria (any data-isolation issue, consent issue, or > 10% failed jobs → pause the tenant).
```

Done when: wave 1 school passes the check and starts uploading.

---

### P8.9 · Daily pilot health report

```text
Create scripts/daily_report.py (runs each morning via beat, emails me): per tenant for the last 24 h —
uploads, completed, failed (with top error codes), needs review, median and p95 turnaround, GPU utilisation,
LLM cost per audio hour (from llm_calls), disputes opened, quota usage. Highlight anything outside SLO. Only
real measured numbers; show "no data" where empty.
```

Done when: the report arrives every morning during the pilot.

---

### P8.7 · Feedback log and dispute review

Plan task 8.7.

```text
Create a lightweight feedback system: feedback collection {tenant_id, source (call, whatsapp, in-app),
category (bug, accuracy, usability, request), severity, text, linked recording, status}; an in-app
"Send feedback" button on reports; an admin list with filters; a weekly export to docs/pilot/feedback-<week>.md
summarising themes, linked disputes and their resolutions, and candidate rubric changes (to evaluate on the
train split later, never applied directly).
```

Done when: every pilot call or message ends up as a logged item.

---

### Hotfix template

```text
/fix <paste the error, logs, recording id and what the user saw>
Production rule: smallest safe change, test first, deploy with scripts/deploy_prod.sh, verify on the affected
recording, and add a runbook note if it could recur.
```

### Retro template

```text
Read eval/reports/, docs/pilot/feedback-*.md, the DLQ history and the daily reports for the pilot. Write
docs/pilot/retro.md: what worked, what broke (with counts), quality results vs gates, cost per audio hour
measured, top 10 user requests, and a ranked post-pilot backlog using the plan's "After the pilot" list as the
starting point. Use only data from these files; mark anything unknown.
```
