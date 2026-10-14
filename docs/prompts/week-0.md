# Week 0 — Prep (before engineering starts)

Goal: by Friday the repo exists, design references are in place, rubrics v0 are drafted, the annotation tool runs,
LIS baselines are known, and consent drafts are with the lawyer.

---

## P0.2 · Dev setup and design spike

Plan task 0.2. Read first: `CLAUDE.md`, `docs/design/*.png`, `docs/design/source/Main.dc.html`.

```text
We are starting the Sabha repo. Read CLAUDE.md fully.

1. Create the empty repo skeleton exactly as in the "Repo layout" section of CLAUDE.md, with a README per
   top-level folder (one paragraph each: purpose and what lives there).
2. Add docs/design/tokens.md by reading the design source files in docs/design/source/*.dc.html and the
   screenshots in docs/design/*.png. Extract: the colour palette with a semantic name for each hex value
   (ink, ink-2, muted, line, surface, page background, primary, primary-hover, primary-tint, warning, success,
   danger, and the 5 conversation-type colours), font family (Instrument Sans) and weights, font sizes,
   radii, spacing steps, focus ring, minimum touch size (44px), and status-chip styles. Cite which file each
   value came from.
3. Spike: in apps/web, scaffold Vite + React + TypeScript + Tailwind, map tokens.md into tailwind.config.ts,
   and build ONE page, src/spike/OverviewSpike.tsx, that reproduces docs/design/01-overview.png with static
   data. Match layout, spacing, colours and type closely. No routing, no API yet.
4. Write docs/adr/0001-repo-and-stack.md recording the stack from CLAUDE.md.

Out of scope: backend code, auth, real data.
Show me the plan first.
```

Done when: `pnpm -C apps/web dev` shows the overview spike looking like the design screenshot.

---

## P0.5 · Cloud accounts and environment template

Plan task 0.5. Read first: `CLAUDE.md` (stack, golden rule 12).

```text
Create the environment and cloud scaffolding for Sabha. Do not create any cloud resources yourself.

1. .env.example listing every setting the system will need, grouped and commented: Mongo URI (replica set),
   Redis URL, S3 bucket/region (ap-south-1)/endpoint (MinIO locally), OIDC issuer/audience/client id,
   Sentry DSN, Langfuse keys, LLM provider keys (one block per provider, all optional), SES region and sender,
   APP_ENV, LOG_LEVEL, CORS origins, GPU device id, artefact version tags.
2. packages/core/sabha_core/settings.py using pydantic-settings that loads and validates these, fails fast
   with a clear message when a required value is missing, and never logs secret values.
3. scripts/check_env.py that connects to Mongo (and confirms it is a replica set), Redis, S3/MinIO
   (put/get/delete a test object under a "healthcheck/" prefix) and the OIDC discovery URL, printing
   PASS/FAIL per service.
4. docs/setup/cloud-checklist.md: a step-by-step checklist for me to create the AWS account (ap-south-1),
   S3 buckets with block-public-access and lifecycle rules, an IAM user/role with least privilege for the
   app, MongoDB Atlas M10 in Mumbai, GitHub org and repo, Sentry project, billing alerts.

Tests: unit tests for settings validation (missing value, malformed URI, secret not in repr).
```

Done when: `uv run python scripts/check_env.py` prints PASS for every service on your machine.

---

## P0.6 · LLM provider comparison sheet

Plan task 0.6. Read first: `CLAUDE.md` (golden rules 8 and 12).

```text
Create docs/llm-providers.md: a comparison template I will fill in from provider documents and emails.
Columns: provider, models we would use (mid-tier, small), India region available (yes/no/how), data retention
policy, training-on-our-data policy, DPA available, structured output / JSON schema support, prompt caching,
batch API and discount, rate limits, price per million input/output tokens, source link, date checked.
Leave every value blank with "TBD" — do NOT fill in facts from memory. Add a short "Decision rule" section:
data residency first, then agreement with human raters in the bake-off, then cost.
Also write the email text I can send each provider asking for the data-residency and retention terms.
```

Done when: the sheet and email exist; you send the emails.

---

## P0.7 · Collect LIS eval-harness baselines

Plan task 0.7. Read first: the LIS repo's eval harness (give Claude Code the path).

```text
I will give you the path to our Lecture Intelligence System (LIS) repo. Its eval harness compares Qwen3-ASR,
NVIDIA Parakeet, AI4Bharat IndicConformer and faster-whisper.

1. Read the harness and find where results are stored.
2. Write eval/baselines/collect_lis.py that reads the latest results and produces
   eval/baselines/lis-baselines.md: one table per language mix (English, Hindi, Hinglish) with model,
   WER, CER, real-time factor, GPU memory, and the dataset/hours each figure came from.
3. If a figure is not present in the results, write MISSING. Never estimate or fill gaps.
4. Add eval/targets.yaml with Gate 1 targets left as null and a comment that I will set them from this table.

Show me which result files you found before writing the script.
```

Done when: the baseline table exists and you have set Gate 1 targets in `eval/targets.yaml`.

---

## P0.8 · Rubric v0 drafts (teaching and reception)

Plan task 0.8. Read first: `CLAUDE.md`, the plan's "Requirements and the parameter (rubric) model" section.

```text
Draft two rubric files for review with an academic head. They are drafts for humans, not final.

rubrics/teaching.school.v0.1.yaml and rubrics/reception.school.v0.1.yaml, each with:
- id, segment (school), version, roles (teaching: teacher, students; reception: receptionist, caller)
- dimensions: key, name, weight (weights sum to 1.0), definition (one sentence), min_quotes,
  scale anchors for 1, 2, 3, 4 and 5 (one concrete sentence each, observable behaviour only),
  and one short Hinglish example utterance for levels 1 and 5
- computed_metrics: list of metric keys this rubric shows
- output: the report sections (summary, strengths, gaps, suggestions; reception adds category, status,
  follow_up)
- visibility_gate: {metric: cohens_kappa, min: 0.60}

Teaching dimensions: concept_clarity, use_of_examples, checks_for_understanding, questioning_quality, pacing,
recap_and_closure. Reception dimensions: intent_captured, information_accuracy, courtesy, resolution,
escalation_handling.

Also write docs/rubrics/review-sheet.md: a one-page table version of each rubric for the academic head to
mark up on paper. No Python yet.
```

Done when: you and an academic head have agreed the anchors; save the agreed version as v0.2.

---

## P4.1 · Annotation tool for gold transcripts and speaker turns

Plan task 4.1. Read first: `CLAUDE.md` (golden rule 6).

```text
Set up Label Studio for our human annotators.

1. infra/annotation/docker-compose.yml running Label Studio with persistent storage, behind basic auth,
   bound to localhost by default.
2. infra/annotation/transcript_config.xml: a labelling interface that shows audio with a waveform,
   lets annotators mark speaker segments (labels: Teacher, Student(s), Receptionist, Caller, Other, Silence)
   and type the exact transcript per segment (Hinglish allowed, Roman or Devanagari as spoken).
3. eval/goldset/import_tasks.py: takes a folder of audio files plus a manifest CSV
   (file, tenant, type, language_mix, room_type, consent_ref) and creates Label Studio tasks; refuses any row
   without consent_ref.
4. eval/goldset/export_gold.py: exports completed annotations to eval/goldset/gold/<recording>.json in our
   canonical transcript schema (segments with speaker role, start_ms, end_ms, text).
5. docs/annotation-guidelines.md: plain-language rules for annotators (verbatim, fillers, code-switching,
   overlaps, inaudible marks, numbers, names to anonymise), with 5 worked examples.

Tests: export_gold on a small fixture export produces valid canonical JSON.
```

Done when: an annotator can open a pilot recording, label speakers, type the transcript, and export it.

---

## P8.1 · Consent and recording-notice drafts (for the lawyer only)

Plan task 8.1. These are drafts for legal review, never final legal text.

```text
Draft documents for our lawyer to review. Mark every file "DRAFT FOR LEGAL REVIEW — NOT LEGAL ADVICE".

docs/legal/drafts/:
1. parent-consent-form.md: plain-language consent for recording classroom lessons for teacher development
   under India's DPDP Act, 2023: what is recorded, why (staff feedback only, no student scoring), who sees it,
   where data is stored (India), retention (90 days for audio by default), how to withdraw, contact.
   Provide English and Hindi versions side by side.
2. staff-consent-and-notice.md: notice for teachers, counsellors and front-desk staff.
3. call-recording-notice.md: a 10-second spoken notice for reception calls, English and Hindi.
4. questions-for-lawyer.md: the open questions (verifiable parental consent mechanism, children's data
   obligations, role of the school vs Schoollog as data fiduciary/processor, retention, cross-border LLM use).
Do not claim compliance anywhere.
```

Done when: the drafts are sent to the lawyer.
