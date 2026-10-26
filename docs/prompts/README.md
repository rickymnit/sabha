# Claude Code prompts for Sabha

One prompt per task in the 8-week execution plan. Prompt IDs match the plan's sub-problem IDs
(for example `P2.4` builds sub-problem 2.4), so your tracker, the plan and these prompts line up.

## Setup (once)

1. Copy this kit into the root of the `sabha` repo: `CLAUDE.md`, `.claude/commands/`, `docs/`.
2. Open the repo in VS Code and start Claude Code. It reads `CLAUDE.md` automatically every session.
3. Custom commands now available: `/review`, `/tenant-check`, `/gate-check 1|2|3`, `/fix <description>`.

## How to run each prompt

1. Start a **fresh Claude Code session per prompt** (or `/clear`), so context stays small and on-task.
2. Switch to **plan mode** (Shift+Tab) and paste the prompt. Read the plan; correct it before any code is written.
3. Approve, let it implement, then run `make test` and `make lint` yourself.
4. Run `/review` on the diff. Fix FAILs before committing.
5. Commit with the prompt ID in the message: `P2.4: celery queues per stage with DLQ`.
6. Tick the matching sub-problem in the execution plan.

## Order and files

Only work that is not finished is listed (updated 2026-10-26). Tasks marked "partly built" carry a status note under
their heading saying what exists and what remains; some of those notes are older than the commits that followed, so
check `git log` too. Removed prompts are in git history.

Since 2026-10-24 the order is **product first**: more conversation types and the coaching loop in weeks 2–7, and all
infrastructure (AWS, Auth0, deploy, CI/CD, monitoring) together in week 8.

**1. Product (now)**

| Task | File | What remains |
| --- | --- | --- |
| P2.8 re-analysis | `week-5.md` | Not started |
| P6.9 consent (partly built) | `week-6.md` | Consent records (scope, validity), releasing recordings awaiting consent, the admin UI and the upload selector |
| P2.6 live status | `week-2.md` | Not started (server-sent events for the recordings list and overview) |
| P6.8 role views | `week-6.md` | Not started; includes the workspace setup, rubric editor and plans pages in `docs/design/` |
| P6.2 app shell (partly built) | `week-1.md` | Tenant switcher, nav counts, plan usage block, lint rule against hard-coded nouns |
| P1.7 profiles and labels (partly built) | `week-2.md` | `POST /v1/admin/tenants`, `PATCH /v1/settings`, `useLabels()`, blocking disabled types |
| P1.8 audit log (partly built) | `week-2.md` | `GET /v1/audit` and the immutability tests |
| P2.7 notifications (partly built) | `week-5.md` | Webhook settings and the delivery task (signing is built); emails are done |
| P7.2 limits and quotas (partly built) | `week-5.md` | Limiter in the auth dependency, quota checks on upload, lane by duration, admission ETA |
| P7.3 backups, retention, erasure | `week-6.md` | Not started |
| P7.8 admin ops (partly built), P8.6 usage export | `week-7.md` | Admin endpoints and UI, replay and abandon, usage export for invoicing |

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

### Removed because they are done (or dropped)

| Task | Follow-up still open |
| --- | --- |
| P0.2 dev setup and design spike, P0.5 env template, P0.8 rubric v0.1 drafts, P4.1 annotation tool, P1.1 monorepo, P1.4 API skeleton, P6.1 design system, P8.3 recording guide, P5.4 rubric schema, P5.5 computed metrics, P4.4 rater kit | None |
| P0.6 LLM provider | OpenAI `gpt-6-luna` since 2026-10-24 (o3-mini was shut down); data residency terms and settings to confirm with OpenAI (`docs/llm-providers.md`) |
| P0.7 LIS baselines | Dropped: there is no LIS codebase. ASR providers are compared on our own gold set instead |
| P8.1 consent drafts | With the lawyer; sign-off is a people task (plan 8.5) |
| P1.2 CI | The `images` job stays off until the repository variable `PUBLISH_IMAGES` is `true`; turn it on once the Celery app (P2.4) exists |
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
| Sales meetings (rubric `sales.company.v0.2`, deal card), meetings (`meeting.company.v0.1`, ADR 0008) | Added 2026-10-24 to 2026-10-26; no prompt file |
| Company reception: walk-in visitors (`reception.company.v0.1`), the ticket on the report with verified quotes | Draft rubric for the owner's review; a full run on audio once Sarvam has credit |
| P6.7 disputes: raise, the Disputes tab in Reviews, decide, email; the reviewer's score counts in the overall and trends | Calibration records are stored on each dispute; reading them into the calibration loop is P5.9 |

## Coverage check

Every engineering sub-problem in the plan (59 of 67) has a prompt. The 8 remaining sub-problems need people,
not code: 0.1 approval, 0.3 pilot schools, 0.4 recordings, 4.2 gold transcripts (people correct; P4.2 builds
the tooling), 4.5 rater scoring (P4.4 builds the kit), 8.1 and 8.2 legal documents (P8.1 drafts for the
lawyer only), 8.5 legal sign-off. Extra prompts cover gaps the plan implied but did not list as separate
items: notifications (P2.7), re-analysis (P2.8), consent UI (P6.9), admin operations (P7.8), daily health
report (P8.9).

## Prompt-writing tips when you add your own

- Name the files to read first, the exact output, and the test that proves it works.
- State what is out of scope, so Claude Code does not wander.
- Paste error output and logs verbatim instead of describing them.
- For anything touching data access, auth, money or quality numbers, ask for tests first.
