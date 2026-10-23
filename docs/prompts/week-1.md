# Week 1 — Foundations and upload

Goal: a logged-in user uploads a large file directly to storage and sees status `UPLOADED`.

---

## P1.3 · Staging with Docker Compose and Terraform

Plan task 1.3. Read first: `docs/setup/cloud-checklist.md`, `.env.example`.

```text
Create staging infrastructure as code. I will run terraform apply myself after reviewing the plan.

1. infra/terraform/ (AWS ap-south-1): S3 buckets (audio, artefacts, backups) with block public access,
   SSE-KMS encryption, versioning on backups, lifecycle (audio to infrequent access after 30 days, expiry
   configurable per prefix), CORS for presigned browser uploads from our web origin only; a KMS key; an IAM
   role/user for the app with least privilege; 2 EC2 VMs (app VM CPU, GPU VM g6 with L4, or a variable to
   point at our existing on-prem L4 host instead); security groups allowing only 443 publicly; outputs.
2. infra/docker-compose.staging.yml: api, workers-cpu, workers-gpu (with NVIDIA runtime), relay, web, caddy
   (automatic HTTPS), and an otel-collector; MongoDB is Atlas (no local mongo) and Redis runs on the app VM.
3. infra/README.md: how to deploy to staging (pull images by SHA, docker compose up -d, migrations, rollback).
4. scripts/deploy_staging.sh that deploys a given image SHA over SSH and runs a health check.

No secrets in files; read them from the VM's .env written by me.
```

Done when: staging is reachable over HTTPS and `/health` responds.

---

## P6.2 · App shell, login and navigation

> **Status (2026-10-22).** Built: React Router + TanStack Query app shell (`src/app`), sidebar in the tenant's words from /v1/me, problem+json toasts with request id, 401 signs out, protected routes, and the local dev sign-in page (VITE_AUTH_MODE=dev; Auth0 last). Recordings list and report page on the real API. Remaining: tenant switcher, nav counts, plan usage block, the lint rule against hard-coded nouns, Playwright smoke test.

Plan task 6.2. Read first: `docs/design/01-overview.png` (sidebar), P1.5 output.

```text
Build the app shell in apps/web using the design components.

- React Router routes: /login, /, /recordings, /recordings/:id, /upload, /reviews, /people, /rubrics,
  /settings; everything except /login is protected.
- Sidebar exactly like the design: logo, tenant switcher (single tenant for now), nav with counts, conversation
  types list (from tenant enabled_types), plan usage block (static placeholder for now), user block.
- All visible nouns come from the labels returned by GET /v1/me (person, recording, unit); write a useLabels()
  hook and a lint rule or test that fails on hard-coded "Teacher"/"Lesson" in components.
- TanStack Query client with auth header injection and problem+json error handling (toast with request_id).
- Responsive: sidebar stacks above content on phones.

Tests: protected route redirects; labels render from /v1/me; Playwright smoke test logs in (mock OIDC in dev).
```

Done when: you log in on staging and see the shell with your tenant's labels.
