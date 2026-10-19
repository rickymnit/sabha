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

## P2.1 · Create recording and presigned multipart upload

Plan task 2.1. Read first: `CLAUDE.md` golden rules 2 and 9, API conventions.

```text
Implement POST /v1/recordings.

Request: {type: teaching|reception|counselling|meeting|sales, person_id?, unit_id?, file_name, size_bytes,
content_type, consent_ref?, recorded_at?} and an Idempotency-Key header (required).
Behaviour:
- Validate type is in the tenant's enabled_types; content type/extension in
  mp3,m4a,wav,ogg,webm,mp4; size <= 1 GB.
- Store the idempotency key per tenant (Redis + Mongo fallback, 24 h); a replay returns the same response.
- Insert recording with status CREATED and storage_key {tenant_id}/{recording_id}/original/<safe file name>.
- Start an S3 multipart upload; return recording_id, upload_id, part_size (e.g. 16 MB) and presigned URLs
  for every part (15-minute expiry), plus an endpoint to fetch more URLs: POST /v1/recordings/{id}/parts
  {part_numbers:[...]} for resumed uploads.
- Write an audit_log entry.
Service code lives in apps/api/services/recordings.py; routers stay thin.

Tests: happy path against MinIO, idempotent replay, disabled type rejected, oversize rejected, tenant B
cannot request parts for tenant A's recording.
```

Done when: a script can upload a 500 MB file part by part using the returned URLs.

---

## P2.2 · Complete upload, checksum and duplicate detection

> **Status (2026-10-19).** `transition()` / `transition_async()` exist (P2.3, sabha_core/state.py): use them for CREATED → UPLOADED instead of a stub. They also enforce golden rule 9 (no consent_ref, nothing moves past UPLOADED). Use `sabha_api.idempotency` for the Idempotency-Key.

Plan task 2.2.

```text
Implement POST /v1/recordings/{id}/complete {parts:[{part_number, etag}], sha256}.

- Complete the S3 multipart upload; verify object size matches size_bytes.
- The client sends a SHA-256 computed in the browser (Web Crypto, streamed). Store it. If another recording
  in the same tenant has the same sha256 and is not FAILED, mark this one duplicate_of=<id>, status stays
  UPLOADED, and return 409 with code "duplicate_recording" unless the request has force=true.
- If consent_ref is missing, keep status UPLOADED with flag awaiting_consent=true and do not enqueue.
- Otherwise transition CREATED → UPLOADED through the state machine helper (stub it now; P2.3 builds it) and
  leave a TODO hook where P2.5 will write the outbox event.
- Abort and clean up multipart uploads older than 24 h with a periodic task stub (scheduled in P2.4).

Tests: size mismatch fails, duplicate detection, force=true path, missing consent does not enqueue.
```

Done when: a duplicate upload is caught and a normal upload reaches `UPLOADED`.

---

## P6.2 · App shell, login and navigation

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
