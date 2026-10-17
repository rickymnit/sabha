# Week 4 — Scoring engine and the teaching report

Goal: a real lesson gets a full report with verified, playable quotes.

---

## P5.6 · Scoring calls and the grounding verifier

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

## P5.7 · Synthesis, schema validation and storage

> **Status (2026-10-17).** Already built: synthesis, `analysis@v1` schema validation and the report builder (sabha_analytics/synthesis.py, report.py). Remaining: store analyses and scores through TenantRepo and finish the analyze stage.

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
