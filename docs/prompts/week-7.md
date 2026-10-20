# Week 7 — Hardening and pilot readiness

Goal: the system survives a bad day, production is live with alerts, and schools are ready.

---

## P7.5 · Load and chaos tests

Plan task 7.5.

```text
Build infra/loadtest/ with k6 (or Locust if you prefer; say why).

Scenarios against staging (never production):
1. Burst: 300–500 lecture uploads (use 5 real-length test files reused with different ids; consent records for
   a test tenant) over 30 minutes from 3 tenants, plus a steady trickle of 5-minute reception calls.
2. API: 50 concurrent users browsing overview, reports and transcripts.
Measure: upload success rate, p95 upload-to-result for 60-min files and short calls, queue age per queue,
GPU utilisation, error rates, LLM cost per audio hour. Compare with SLOs in docs/slo.md (write it from CLAUDE.md
and the plan: 99.5% API availability, 60-min file p95 <= 30 min, short call p95 <= 5 min, >= 99% job success).

Chaos script (scripts/chaos.sh): kill a CPU worker mid-job, restart the GPU worker, restart Redis, stop the relay
for 2 minutes, drop Mongo primary (Atlas test failover). Verify no lost or duplicated jobs.
Write results to eval/reports/load-<date>.md. Never invent results; if a run is incomplete, say so.
```

Done when: p95 targets are met with zero lost jobs, or the report states exactly what failed.

---

## P7.6 · Security checks

> **Status (2026-10-19).** Started: `docs/security/findings.md` (pip-audit clean; pnpm audit: one high and one moderate, both build-time Tailwind 3 dependencies, accepted with reasons; the three /tenant-check findings fixed). Remaining: the checks listed there under "Not run yet" (ZAP, trivy, bucket policies and IAM, webhook SSRF, ffmpeg protocol whitelist, secrets rotation).

Plan task 7.6.

```text
Run a security pass and fix what it finds.
- Dependency and image scanning (pip-audit, pnpm audit, trivy on our images); fix highs.
- OWASP ZAP baseline scan against staging (authenticated); triage findings in docs/security/zap-<date>.md.
- Review: JWT validation, CORS, security headers, cookie flags, presigned URL scopes and expiry, S3 bucket
  policies, IAM least privilege, rate limits, error messages not leaking internals, logs not containing PII or
  secrets, admin endpoints protected, SSRF in webhook URLs (block private ranges), file-type handling in
  ffmpeg (no arbitrary protocol access: use -protocol_whitelist file).
- Secrets rotation procedure in the runbook.
Output a findings table with severity, status and fix commit.
```

Done when: no high-severity findings remain open.

---

## P7.7 · Production deploy, alerts and runbook

Plan task 7.7.

```text
Prepare production for the pilot.
- infra/docker-compose.prod.yml mirroring staging with prod settings; Terraform workspace for prod;
  separate buckets, KMS key, Atlas cluster and credentials; daily backups verified.
- Deployment: scripts/deploy_prod.sh with a manual approval step, health checks, and one-command rollback to
  the previous image SHA.
- Alerts (Grafana alerting to my phone via a Telegram/WhatsApp/email channel — ask me which): SLO burn rate,
  DLQ growth (> 10 in 1 h), GPU worker down, queue age above threshold, error-rate spike, backup failure,
  certificate expiry, LLM spend above daily budget.
- docs/runbook.md: architecture overview, how to deploy and roll back, how to replay DLQ jobs, how to restore a
  backup, what each alert means and the first 3 steps for it, how to pause a tenant, how to rotate secrets,
  contact list.
```

Done when: a test alert reaches your phone and a rollback has been rehearsed.

---

## P7.8 · Admin operations tools

> **Status (2026-10-19).** Partly built: `scripts/admin/create_tenant.py` creates a tenant and invites its first owner; dead letters are written to `dlq` with replay arguments (P2.4); stage runs carry a heartbeat. Remaining: the admin endpoints and UI, replay, abandon, pause/resume, the recording timeline and `seed_demo.py`. Decide who the cross-tenant "internal admin" is.

Implied by the dead-letter queue and pilot operations.

```text
Build internal admin tooling (owner/internal-admin only, all audited):
- /admin/jobs: DLQ list with error code and context; replay from the last finished stage; mark as abandoned.
- /admin/recordings/{id}: full stage_runs timeline, artefacts list, trace link, cost breakdown.
- /admin/tenants: create a tenant from a profile, set plan and quota, pause/resume processing.
- scripts/seed_demo.py: creates a demo tenant with synthetic (non-real) recordings and reports for training
  sessions, clearly labelled "Demo data".
Tests: replay is idempotent; pause stops new processing for that tenant only.
```

Done when: you can replay a failed job and create a pilot tenant in under 2 minutes.

---

## P8.4 · Pilot onboarding pack

Plan task 8.4.

```text
Create the pilot onboarding pack in docs/pilot/:
- coordinator-training.md: a 45-minute session outline (log in, invite staff, consent records, upload, read a
  report, dispute a score, what the scores mean and do not mean).
- staff-faq.md (English and Hindi): what is recorded, who sees reports, how scores work, how to dispute, privacy.
- quick-start.md with step-by-step screenshots placeholders I will fill from the real app.
- support.md: how pilot users get help (WhatsApp group rules, response times), and how we log issues.
- An in-app "Help" link and first-login welcome checklist for coordinators (small frontend task).
```

Done when: each pilot school has a trained coordinator.

---

## P8.6 · Usage export and manual invoicing

Plan task 8.6.

```text
Implement the billing.meter stage and exports.
- On COMPLETED (first analysis only), write usage_events {tenant_id, recording_id (unique), audio_seconds
  (original duration), type, period (YYYY-MM, IST)}; re-analysis and failed jobs are never billed.
- GET /v1/usage?period=YYYY-MM (owner/admin): totals by type and by unit.
- scripts/invoice_export.py: CSV per tenant per month with included hours, overage hours, and amounts from the
  plan table in config (prices filled by me), plus 18% GST lines; marked "pilot — manual invoice".
Tests: uniqueness prevents double billing; period boundaries in IST.
```

Done when: usage per school for a month exports correctly.

---

## Gate 3 review

```text
Create docs/gate3-checklist.md from the plan's Gate 3 criteria, then run /gate-check 3.
```

Go live only if every item is PASS, including legal sign-off and consent records.
