# Week 5 — Reception, disputes and fairness

Goal: both conversation types work, staff can dispute scores, and one busy school cannot slow the others.

---

## P5.8 · Classify, segment and the reception rubric

> **Status (2026-10-17).** Already built: classify step, phase segmentation, reception ticket and hold-gap metric (sabha_analytics). Remaining: publish `rubrics/reception.school.v1.0.yaml` (needs the academic head's v0.2) and wire both steps into the analyze stage.

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

> **Status (2026-10-17).** Already built: the dispute dialog and `/reviews` page on mock data (`/dev/reviews`). Remaining: the three endpoints, the `disputes` collection, override scores with history, calibration records, and the resolution notification.

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

## P7.2 · Rate limits, quotas, priority lanes and fair scheduling

> **Status (2026-10-17).** Already built: the fair GPU scheduler and ADR 0005, the Redis token-bucket rate limiter, quota rules and priority-lane routing. Remaining: call the limiter from the auth dependency (with a per-tenant user key, /tenant-check finding 1), quota checks in the upload API with the 80% banner, the `gpu.speech` dispatcher, and the admission-control ETA.

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

> **Status (2026-10-17).** Already built: notification rules, English and Hindi templates, signed webhooks, the SES adapter. Remaining: the `io.notify` Celery task, the delivery log in MongoDB keyed by (tenant_id, delivery_key) (/tenant-check finding 3), per-user preferences, webhook retries and delivery log.

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

> **Status (2026-10-17).** Already built: the overview UI, "Where coaching helps most" panel and IST date-range picker on mock data (`/dev/overview`). Remaining: `GET /v1/overview` aggregations through TenantRepo and the nightly weekly summary (`$merge` needs a vetted repository method, see `sabha_core/repo.py`).

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
