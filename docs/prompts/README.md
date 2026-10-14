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

| File | Week | Prompts |
| --- | --- | --- |
| `week-0.md` | Prep | P0.2 dev setup and design spike, P0.5 cloud and env, P0.6 LLM provider sheet, P0.7 LIS baselines, P0.8 rubric v0, P4.1 annotation tool, P8.1 consent drafts |
| `week-1.md` | Foundations | P1.1 monorepo, P1.2 CI, P1.3 compose and Terraform, P1.4 API skeleton, P1.5 identity, P1.6 tenancy, P2.1 recordings and upload, P2.2 complete and dedupe, P6.1 design system, P6.2 app shell, P8.3 recording guide |
| `week-2.md` | Orchestration and audio | P2.3 state machine, P2.4 queues and DLQ, P2.5 outbox relay, P2.6 SSE, P1.7 labels and profiles, P1.8 audit log, P3.1 ASR port, P3.2 normalise, P3.3 VAD and segment map, P3.4a diarization, P6.3 upload screen, P6.4a overview shell, P7.1 monitoring |
| `week-3.md` | Speech and Gate 1 | P3.4b diarization finish, P3.5 ASR batching, P3.6 roles, P3.7 transcript assembly, P4.2 gold-set tooling, P4.3 WER and role eval, P5.1 LLM gateway, P5.2 PII redaction, P5.3 model bake-off, P6.5 transcript view, Gate 1 |
| `week-4.md` | Scoring | P5.4 rubric schema, P5.5 computed metrics, P5.6 scoring and grounding, P5.7 synthesis and validation, P5.7b analysis API, P4.4 rater kit, P6.6 report page |
| `week-5.md` | Reception and fairness | P5.8 classify, segment, reception rubric, P6.7 disputes and reviews, P4.6 kappa and grounding eval, P7.2 limits, quotas and lanes, P2.7 notifications, P2.8 re-analysis, P6.4b overview with real data |
| `week-6.md` | Calibration and Gate 2 | P5.9 calibration loop, P4.7 CI eval gate, P7.3 backups, retention, erasure, P7.4 isolation tests, P6.8 role views, P6.9 consent in UI, Gate 2 |
| `week-7.md` | Hardening | P7.5 load and chaos, P7.6 security, P7.7 production and alerts, P7.8 admin ops (DLQ replay, seed tenant), P8.4 onboarding pack, P8.6 usage export, Gate 3 |
| `week-8.md` | Pilot | P8.8 go-live checklist, P8.9 daily health report, P8.7 feedback log, hotfix and retro templates |

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
