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

Only work that is not finished is listed (updated 2026-10-17). Tasks marked "partly built" carry a status note under
their heading saying what exists and what remains. Removed prompts are in git history.

| File | Week | Prompts still to do |
| --- | --- | --- |
| `week-1.md` | Foundations | P1.3 compose and Terraform, P1.5 identity (partly built), P1.6 tenancy (partly built), P2.1 recordings and upload, P2.2 complete and dedupe, P6.2 app shell |
| `week-2.md` | Orchestration and audio | P2.3 state machine (partly built), P2.4 queues and DLQ, P2.5 outbox relay, P2.6 SSE, P1.7 labels and profiles (partly built), P1.8 audit log, P3.2 normalise, P3.3 VAD and segment map (partly built), P3.4a diarization, P6.3 upload screen, P6.4a overview shell, P7.1 monitoring (partly built) |
| `week-3.md` | Speech and Gate 1 | P3.4b diarization finish, P3.5 ASR stage (partly built), P3.6 roles (partly built), P3.7 transcript assembly (partly built), P5.1 LLM gateway, P5.3 model bake-off, Gate 1 |
| `week-4.md` | Scoring | P5.6 scoring and grounding (partly built), P5.7 synthesis and storage (partly built), P5.7b analysis API |
| `week-5.md` | Reception and fairness | P5.8 classify, segment, reception rubric (partly built), P6.7 disputes and reviews (partly built), P7.2 limits, quotas and lanes (partly built), P2.7 notifications (partly built), P2.8 re-analysis, P6.4b overview with real data (partly built) |
| `week-6.md` | Calibration and Gate 2 | P5.9 calibration loop, P4.7 CI eval gate, P7.3 backups, retention, erasure, P7.4 isolation tests, P6.8 role views, P6.9 consent in UI, Gate 2 |
| `week-7.md` | Hardening | P7.5 load and chaos, P7.6 security, P7.7 production and alerts, P7.8 admin ops (DLQ replay, seed tenant), P8.4 onboarding pack, P8.6 usage export, Gate 3 |
| `week-8.md` | Pilot | P8.8 go-live checklist, P8.9 daily health report, P8.7 feedback log, hotfix and retro templates |

### Removed because they are done (or dropped)

| Task | Follow-up still open |
| --- | --- |
| P0.2 dev setup and design spike, P0.5 env template, P0.8 rubric v0.1 drafts, P4.1 annotation tool, P1.1 monorepo, P1.4 API skeleton, P6.1 design system, P8.3 recording guide, P5.4 rubric schema, P5.5 computed metrics, P4.4 rater kit | None |
| P0.6 LLM provider | OpenAI o3-mini chosen; availability, data residency terms and settings to confirm with OpenAI (`docs/llm-providers.md`) |
| P0.7 LIS baselines | Dropped: there is no LIS codebase. ASR providers are compared on our own gold set instead |
| P8.1 consent drafts | With the lawyer; sign-off is a people task (plan 8.5) |
| P1.2 CI | The `images` job stays off until the repository variable `PUBLISH_IMAGES` is `true`; turn it on once the Celery app (P2.4) exists |
| P3.1 ASR provider layer (Sarvam AI, ADR 0006) | "Done when" needs a valid `SARVAM_API_KEY` (the current one is rejected with 403) and Sarvam's data terms in writing before real audio |
| P4.2 gold-set tooling, P4.3 WER and role eval, P4.6 kappa and grounding eval | Tools built; run them on the real gold set and rater scores once those exist |
| P5.2 PII redaction | Built with regular expressions; CLAUDE.md names Presidio. Decide whether to adopt Presidio |
| P6.5 transcript view, P6.6 report page | Built on mock data; real data arrives with P6.2 and P5.7b |

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
