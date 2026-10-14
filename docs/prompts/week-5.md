# Week 5 — Reception, disputes and fairness

Goal: both conversation types work, staff can dispute scores, and one busy school cannot slow the others.

---

## P5.8 · Classify, segment and the reception rubric

Plan task 5.8. Read first: `rubrics/reception.school.v0.2.yaml`.

```text
Extend the analyze stage.

- Classify step (small tier): if the uploader did not set the type, or set_type_confidence is low, classify
  the conversation type and language mix from the first 3 minutes of redacted text; low confidence →
  NEEDS_REVIEW (reason uncertain_type).
- Segment step (small tier): split into phases from the rubric's phase list (teaching: introduction,
  explanation, guided practice, closing; reception: greeting, need, information, resolution, close) with
  utterance-id boundaries; verify boundaries exist; store for the timeline.
- Publish rubrics/reception.school.v1.0.yaml. Reception output adds: category (complaint, information, fee,
  admission, other), resolution status (resolved, pending, escalated), follow_up (text + owner role), and a
  ticket-style summary.
- Reception computed metrics: handle time, hold or silence gaps > 10 s, caller talk share.
Tests: fixture reception call yields a valid report; misclassified-type path goes to NEEDS_REVIEW.
```

Done when: 10 real calls produce ticket-style reports.

---

## P6.7 · Disputes and reviews

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

## P4.6 · Agreement and grounding evaluation

Plan task 4.6. Read first: `CLAUDE.md` golden rule 6.

```text
Implement eval/kappa.py and eval/grounding.py (make eval-kappa).

- Split: assign each calibration recording to train or holdout once (stratified by school and type, seeded),
  stored in eval/calibration/split.json; the holdout is never used for tuning.
- Human reference per dimension = median of the 3 raters.
- Report per rubric and dimension: quadratic-weighted Cohen's kappa between AI and human reference, rater-rater
  agreement for context, exact and within-1 agreement, bootstrap CI, n.
- grounding.py: share of evidence quotes verified, per model and prompt version; share of dimensions excluded.
- Output eval/reports/kappa-<date>.md/.json; mark each dimension PASS (>= 0.60) or FAIL against eval/targets.yaml.
Tests: hand-computed kappa on a toy set; split is deterministic and holdout untouched by tuning code paths.
```

Done when: the first per-dimension agreement table is produced on real rater scores.

---

## P7.2 · Rate limits, quotas, priority lanes and fair scheduling

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

## P2.7 · Notifications

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

## P2.8 · Re-analysis

Implied by the plan's re-analysis endpoint.

```text
Implement POST /v1/recordings/{id}/reanalyze {rubric_version?, reason} (admin/owner): reuses the existing
transcript (no ASR), transitions COMPLETED → ANALYZING, creates a new analyses version, keeps old versions,
and is not billed as new audio hours. Bulk variant for admins: re-analyse all recordings for a rubric version
change, rate-limited. Tests: transcript not recomputed; usage not double-counted; history preserved.
```

Done when: changing a rubric and re-analysing keeps both versions visible.

---

## P6.4b · Overview with real numbers

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
