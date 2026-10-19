# Week 6 — Calibration, Gate 2 and feature freeze

Goal: AI scores agree with human raters on the hold-out set, and nothing new is added after Friday.

---

## P5.9 · Calibration loop (train split only)

Plan task 5.9. Read first: `eval/calibration/split.json`, latest `eval/reports/kappa-*.md`.

```text
Help me improve agreement WITHOUT overfitting.

1. Using ONLY the train split, list for each dimension below 0.60: the recordings with the largest AI-human gaps,
   the AI rationale and evidence, the raters' notes.
2. Classify the cause per case: unclear anchor wording, prompt instruction issue, transcript/ASR error,
   role error, genuine rater disagreement.
3. Propose specific changes (anchor wording in the rubric YAML, prompt wording) as a diff — do not apply yet.
4. After I approve, bump rubric/prompt versions, re-run scoring on the train split, then run
   `make eval-kappa` on the HOLDOUT split exactly once for this iteration, and log it in
   eval/reports/calibration-log.md (iteration, changes, train kappa, holdout kappa).
Rules: never look at holdout cases while proposing changes; never change the rubric meaning to match the AI;
stop after 3 iterations and report.
```

Done when: holdout kappa is reported per dimension; dimensions under 0.60 become admin-only.

---

## P4.7 · Evaluation gate in CI

Plan task 4.7.

```text
Add a regression gate.

- eval/regression/: a small fixed set (10 recordings with gold transcripts and rater scores) committed as
  manifests (audio stays in the private bucket; CI fetches with read-only credentials).
- .github/workflows/eval-gate.yml: runs on PRs that touch packages/asr, packages/llm, packages/analytics,
  prompts/ or rubrics/; computes WER, grounding pass rate and kappa on the regression set; fails if any metric
  degrades beyond tolerances in eval/targets.yaml compared with the stored baseline on main.
- Posts a summary table as a PR comment.
- LLM calls in CI use a separate budget and are cached by prompt hash to keep cost low.
```

Done when: a deliberately worse prompt fails the PR.

---

## P7.3 · Backups, retention and erasure

Plan task 7.3.

```text
Implement data lifecycle.

- Backups: Atlas continuous backup enabled (document in runbook); nightly export of critical collections to the
  backups bucket as a second copy; scripts/restore_drill.py restores into a scratch database and verifies counts
  and a sample of documents.
- Retention: a nightly job deletes original audio and playback copies older than tenant.retention_days (default
  90), keeps transcripts and scores; writes an audit entry per batch; dry-run mode.
- Erasure (DPDP): POST /v1/admin/erasure {scope: recording|person|tenant, id} (owner) deletes audio,
  artefacts, transcripts, analyses, scores and disputes for the scope, keeps a minimal tombstone and audit log
  entry; returns a report.
Tests: retention deletes only expired audio; erasure removes every collection and S3 prefix for the scope;
restore drill passes on staging.
```

Done when: a restore is rehearsed on staging and the retention job runs nightly.

---

## P7.4 · Tenant-isolation and permission tests

> **Status (2026-10-19).** Already built: `tests/security/permissions.yaml` (reviewed by the owner) and `test_permission_matrix.py`, which fails if an OpenAPI route is missing from the matrix and calls every route as nine callers (anonymous, owner, admin, managers of the recording's unit and another unit, a reviewer, the uploader, a colleague, another tenant). Presigned upload keys are checked to sit under the caller's tenant (`test_recordings.py`). Remaining: add each new route to the matrix as it lands (the test enforces it), the SSE checks (with P2.6), aggregation checks (with P6.4b), and a final `/tenant-check` run.

Plan task 7.4.

```text
Strengthen security tests in tests/security/.

- Generate tests for EVERY route in the OpenAPI spec: for each role (owner, admin, manager, reviewer, staff)
  and for a user from another tenant, assert the expected status per a permission matrix file
  tests/security/permissions.yaml (write the matrix; I will review it).
- S3: presigned URLs are only issued for keys under the caller's tenant prefix.
- SSE: events never cross tenants or reach staff for other people's recordings.
- Aggregations and search queries include the tenant filter.
Run /tenant-check and fix every finding before finishing.
```

Done when: the full permission matrix passes in CI.

---

## P6.8 · Role-based views and polish

Plan task 6.8.

```text
Frontend role behaviour and polish:
- Staff: see only their own recordings and reports; no overview of others; can dispute.
- Manager/reviewer: their units; reviews queue.
- Admin/owner: everything in the tenant, settings, audit log, admin-only (unverified or below-gate) dimensions
  marked "Internal".
- Empty states, loading skeletons, error states with request id, 404 page, session-expiry handling.
- Accessibility pass: keyboard navigation, focus order, contrast check, aria labels on icon buttons.
- Performance: route-level code splitting; report page interactive in under 2 s on staging.
Tests: Playwright per role verifying what is visible and what is not.
```

Done when: a staff account cannot open a colleague's report.

---

## P6.9 · Consent in the product

Covers the consent tick in task 6.3 and golden rule 9.

```text
Enforce consent end to end:
- Tenants store consent records: {consent_ref, scope (school-year class/section, staff member, call line),
  valid_from, valid_to, document_url}. Admin UI to add/edit them.
- Upload screen: consent selector (pre-filled for the person/unit when a valid record exists) plus the
  confirmation checkbox; the API rejects processing when consent_ref is missing, expired or out of scope
  (recording stays UPLOADED with awaiting_consent).
- Report and audit show which consent record covered each recording.
Tests: missing/expired consent blocks the pipeline; valid consent proceeds.
```

Done when: no recording can be processed without a valid consent record.

---

## Gate 2 review

```text
/gate-check 2
```

Feature freeze after Friday: from now on only fixes, tests, docs and operations work.
