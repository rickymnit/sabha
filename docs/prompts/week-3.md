# Week 3 — Speech-to-text, model choices and Gate 1

Goal: real pilot lessons become speaker-labelled transcripts, and the speech and language models are chosen
with measured evidence.

---

## P3.4b · Finish diarization

Plan task 3.4.

```text
Finish diarization: evaluate pyannote vs Sortformer on 5 gold-set files using eval/roles.py once it exists
(P4.3) or a quick DER script; pick one via settings; handle overlapping speech (keep overlaps, mark them);
handle 1-speaker recordings gracefully; add GPU memory guards (OOM → TransientError with smaller batch).
Write docs/adr/0003-diarization.md with the measured comparison (no invented numbers; MISSING if not run).
```

Done when: the chosen diarizer runs reliably on all gold files.

---

## P3.5 · Speech-to-text with batching

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

## P3.6 · Speaker role assignment

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

## P3.7 · Transcript assembly

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

## P4.2 · Gold-set tooling and freeze

Plan task 4.2 (people correct transcripts; this builds the tooling).

```text
Build eval/goldset/:
- manifest.csv schema {recording_id, file, type, language_mix, room_type, duration_s, consent_ref, split
  (dev|holdout), annotator, status}.
- freeze.py: validates every holdout file has a completed gold transcript and speaker labels, computes total
  hours per language mix and room type, writes eval/goldset/FROZEN.json with file hashes, and refuses to run if
  holdout hours < the target in eval/targets.yaml.
- After freezing, any change to a holdout file fails CI (hash check).
- report.py prints coverage: hours by language mix, room type, school.
```

Done when: the hold-out set is frozen at 15–20 hours.

---

## P4.3 · WER and role-accuracy evaluation

Plan task 4.3.

```text
Implement eval/wer.py and eval/roles.py (make eval-wer).

- Text normalisation for Hinglish: lowercase, punctuation stripped, numbers normalised consistently, Devanagari
  and Roman kept as written (report both raw and a transliterated-normalised WER using a documented
  transliteration step).
- WER and CER per file, per language mix, per room type, overall (word-weighted); confidence intervals by
  bootstrap over files.
- roles.py: role accuracy per file (share of reference speech time attributed to the correct role) and DER.
- Output eval/reports/wer-<date>.md and .json; compare against eval/targets.yaml; never print a target as met
  if data is missing.
Tests: known small examples with hand-computed WER; bootstrap reproducible with a seed.
```

Done when: one command prints WER and role accuracy on the hold-out set.

---

## P5.1 · LLM gateway

Plan task 5.1. Read first: `CLAUDE.md` golden rules 5, 7, 8; `docs/llm-providers.md`.

```text
Build packages/llm (sabha_llm): the only way any code calls an LLM.

- Provider adapters (start with the 3 bake-off candidates) behind one interface: complete(messages,
  json_schema?, model_tier: small|mid, temperature=0, max_tokens, cache_hint) → {text|json, usage, cost, latency,
  model_id}.
- Routing by task name → tier → configured model; per-tenant and global token budgets (Redis counters);
  timeouts; retries with jitter on 429/5xx only; explicit fallback list per task, logged with reason (never
  silent).
- Prompt caching support where the provider offers it (stable prefix: system prompt + rubric + transcript).
- Cost accounting from a price table in config (values filled by me, not invented); write usage to an
  llm_calls collection {tenant_id, recording_id, task, model, tokens_in, tokens_out, cached_tokens, cost, ms}.
- Langfuse tracing for every call with prompt hash and version.
Tests with a fake provider: budget exceeded blocks, retry only on retryable codes, fallback logged, JSON schema
enforced (invalid JSON → one repair attempt → error).
```

Done when: every LLM call is traced with tokens and cost.

---

## P5.2 · PII redaction

Plan task 5.2. **Tests first.**

```text
Add redaction in sabha_llm/redact.py, applied automatically inside the gateway before any provider call.

- Microsoft Presidio with custom recognisers: Indian mobile numbers (+91 and 10-digit), Aadhaar-like 12-digit
  patterns (with and without spaces), PAN pattern, emails, and a configurable list of names to mask (school
  staff names are NOT masked by default; student names in teaching transcripts are).
- Replace with stable placeholders per document ([PHONE_1], [STUDENT_2]) and keep the mapping server-side so
  quotes can be shown un-redacted to authorised users after verification.
- Grounding (P5.6) must match quotes against the redacted text, then map back.
Tests first: each pattern, Hinglish sentences, no false positive on times like "10:30" or class names like
"Class 10".
```

Done when: no unmasked phone, Aadhaar-like number or email reaches a provider in tests.

---

## P5.3 · Model bake-off harness

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

## P6.5 · Transcript view with synced player

Plan task 6.5.

```text
Build the transcript panel and audio player used on /recordings/:id.

- Audio player for playback.opus (presigned URL from the transcript endpoint; refresh before expiry);
  play/pause, seek, speed 0.75–2x, keyboard shortcuts.
- Transcript list: time, role (from labels), text; current line highlighted while playing; click a line to
  seek; low-confidence spans styled subtly; search within the transcript.
- Virtualised list for 3-hour recordings.
Tests: click-to-seek, highlight follows playback, virtualisation renders 5,000 lines smoothly.
```

Done when: clicking any line plays that exact moment.

---

## Gate 1 review

```text
/gate-check 1
```

Then update the execution plan's Gate 1 checkbox only if every criterion is PASS.
