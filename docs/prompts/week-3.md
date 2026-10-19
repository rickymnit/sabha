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

> **Status (2026-10-17).** Already built: chunk planning and merging (`chunking.py`), the batcher (`batcher.py`), and the ASR provider layer with Sarvam AI (P3.1, ADR 0006; there are no LIS baselines). Sarvam's REST limit is 30 s per chunk and it gives phrase-level timestamps. Remaining: the transcribe stage on `gpu.speech` writing `asr@v1.json` and recording cost inputs in `stage_runs`.

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

> **Status (2026-10-17).** Already built: heuristic role assignment (`sabha_asr/roles.py`) with tests. Remaining: run it as a pipeline step that writes `roles@v1.json`, with the LLM tie-break and NEEDS_REVIEW path.

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

> **Status (2026-10-17).** Already built: transcript assembly and validation (`sabha_asr/assembly.py`, `transcript.v1.schema.json`), including null confidence and `word_timing`. Remaining: run it in the transcribe stage, store `transcript@v1.json` and the `transcripts` record, and transition to ANALYZING.

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

## Gate 1 review

```text
/gate-check 1
```

Then update the execution plan's Gate 1 checkbox only if every criterion is PASS.
