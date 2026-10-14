# Week 4 — Scoring engine and the teaching report

Goal: a real lesson gets a full report with verified, playable quotes.

---

## P5.4 · Rubric schema, loader and versioning

Plan task 5.4. Read first: `rubrics/teaching.school.v0.2.yaml` (agreed with the academic head).

```text
Build packages/analytics/sabha_analytics/rubric.py.

- A Pydantic schema for rubric files matching the v0 YAML (id, segment, version, roles, dimensions with key,
  name, weight, definition, min_quotes, scale anchors 1–5, examples; computed_metrics; output sections;
  visibility_gate). Validation: weights sum to 1.0 (±0.001), keys unique, all 5 anchors present.
- Loader: reads rubrics/*.yaml, validates, computes a content hash, and upserts into the rubrics collection
  as immutable versions ({type, segment, version} unique). Publishing a changed file without bumping the
  version fails.
- CLI: `uv run sabha-rubric validate|publish|diff <file>`.
- Convert v0.2 to teaching.school.v1.0.yaml as the first published version.
Tests: invalid weights, missing anchors, duplicate version, hash change without version bump.
```

Done when: `sabha-rubric publish rubrics/teaching.school.v1.0.yaml` succeeds.

---

## P5.5 · Computed metrics

Plan task 5.5. **Tests first** with hand-counted fixtures.

```text
Implement sabha_analytics/metrics.py — deterministic, no LLM.

From the canonical transcript, roles and segment stats compute:
- talk share per role (by speech time), turns per role
- teacher questions (utterances ending in "?" plus Hindi/Hinglish question markers: kya, kyun, kaise, kaun,
  kab, kahan, "samajh aaya", "right?", "na?"), split into open vs recall using a small rule list (why/how/
  explain → open), documented in the code
- student questions
- speaking pace (words per minute of the primary role's speech)
- longest uninterrupted turn of the primary role (ms, with start/end on the original timeline)
- silence stats (from segment stats), number of long pauses (> 5 s)
Each metric returns value + a short definition string used in the UI tooltip.
Tests first: 5 fixture transcripts with hand-counted expected values.
```

Done when: metrics match hand counts on all 5 fixtures.

---

## P5.6 · Scoring calls and the grounding verifier

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

## P5.7 · Synthesis, schema validation and storage

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

## P5.7b · Analysis API

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

---

## P4.4 · Rater kit

Plan task 4.4 (raters then score; that work is people, not code).

```text
Build the human-rater kit in eval/raters/:
- export_sheet.py: for a list of recordings, create one Google-Sheets-compatible CSV per rater with rows
  per (recording, dimension), columns for score 1–5 and a short note, plus links to the transcript view; the
  rubric anchors included as a reference tab (CSV) — raters must NOT see AI scores.
- import_scores.py: reads completed CSVs, validates (1–5, every dimension filled), stores in a rater_scores
  collection {recording_id, rater_id, dimension, score, note}.
- practice_agreement.py: agreement among the 3 raters on a practice set (weighted kappa per dimension) to
  confirm they are calibrated before the real set.
- docs/raters/guide.md: how to score, with the anchors and 3 worked examples from the rubric file.
Tests: import validation rejects missing or out-of-range scores.
```

Done when: 3 raters agree on the practice set and start the calibration set.

---

## P6.6 · Recording report page

Plan task 6.6. Read first: `docs/design/02-recording-report.png`, `docs/design/source/Analysis.dc.html`.

```text
Build /recordings/:id matching docs/design/02-recording-report.png, using GET /analysis and /transcript.

Sections: header (title, person, recorded time IST, speech minutes, languages, rubric version link,
Export PDF placeholder, Share button placeholder), overall score with comparison text (only if the comparison
number exists from real data; otherwise hide), summary and 3 suggestions with clickable times, lesson timeline
(phases if available, waveform-style bars coloured by role from diarization, removed-silence shown in grey,
evidence pins for the selected dimension, playhead), "Measured from the transcript" metric strip with
definitions in tooltips, rubric score list (selectable), selected-dimension detail (scale bar, rationale,
evidence quotes with play buttons, "Quotes verified in transcript" badge, suggestion, Dispute button wired in
P6.7), transcript panel (P6.5) with the selected evidence highlighted.
States: processing (live progress), failed (reason + contact), needs review (reason), partial (unverified
dimensions hidden with a note for admins only).
Tests: Playwright: select a dimension → pins move → click evidence → audio seeks to the quote.
```

Done when: the page matches the design on a real pilot lesson.
