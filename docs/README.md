# docs

Written knowledge for the team and for schools and companies. If someone else would need to know it to operate or
change the system, it belongs here. Updated 19 November 2026.

## Start here

| Document | For |
| --- | --- |
| [`../README.md`](../README.md) | What Sabha is, how to run it, project status and running costs |
| [`../commands.md`](../commands.md) | Every command to run Sabha by hand on one machine, and troubleshooting |
| [`../CLAUDE.md`](../CLAUDE.md) | The rules every change must follow |
| [`documentation.md`](documentation.md) | Every document below in one file, with a table of contents. Rebuild it after editing any doc: `uv run python scripts/build_documentation.py` |
| [`runbook.md`](runbook.md) | Operating notes: deploying model changes, backups and the restore drill, audio retention, erasure, backfill |

## Decisions (ADRs)

| ADR | Decision |
| --- | --- |
| [0001](adr/0001-repo-and-stack.md) | Repository layout and technology stack |
| [0002](adr/0002-auth.md) | Auth0 for sign-in; local sign-in until it is set up |
| [0003](adr/0003-local-object-storage.md) | RustFS for local object storage |
| [0005](adr/0005-fairness.md) | Fair scheduling of processing across tenants |
| [0006](adr/0006-asr-sarvam.md) | Sarvam AI for speech recognition, with approximate word timing |
| [0007](adr/0007-review-outcomes.md) | How a recording leaves "Needs review" |
| [0008](adr/0008-meetings.md) | Meetings are analysed as a whole |
| [0009](adr/0009-transcript-upload.md) | Meeting transcripts can be uploaded instead of audio |
| [0010](adr/0010-no-github-actions.md) | No GitHub Actions |
| [0011](adr/0011-evidence-based-speaker-roles.md) | Speaker roles from what each speaker does |
| [0012](adr/0012-more-asr-providers.md) | More speech-to-text providers, the upload list and Gemini's cost per hour |
| [0013](adr/0013-said-well-and-badly.md) | What the agent said well and badly, checked against product information |
| [0014](adr/0014-speaker-count-and-gemini-speaker-check.md) | Number of speakers and the Gemini speaker check, chosen at upload |
| [0015](adr/0015-colleague-helped-calls.md) | Support calls a colleague helped on stay the first agent's |
| [0016](adr/0016-no-automated-tests.md) | Automated tests removed |

## Reference

| Folder or file | Contents |
| --- | --- |
| [`llm-providers.md`](llm-providers.md) | The LLM provider and model (OpenAI `gpt-6-luna`), prices and the questions asked of OpenAI |
| [`webhooks.md`](webhooks.md) | Webhook format and signing (sending is not wired yet) |
| [`security/`](security/) | `findings.md` (security findings and checks) and `permissions.yaml` (who may call every API route) |
| [`design/`](design/) | Design tokens (`tokens.md`) and the v2 page mockups (`v2/`) |
| [`setup/`](setup/) | Setting up Auth0 (`auth.md`) and the AWS checklist (`cloud-checklist.md`), both for week 8 |
| [`annotation-guidelines.md`](annotation-guidelines.md), [`raters/`](raters/), [`rubrics/`](rubrics/) | Building the gold set: transcript annotation, the rater guide and rubric review sheets |
| [`guides/`](guides/) | The recording guide for schools |
| [`legal/drafts/`](legal/drafts/) | Drafts of consent forms and notices, waiting for the law team |
| [`prompts/`](prompts/) | The 8-week plan, one Claude Code prompt per task (history: kept as written) |
