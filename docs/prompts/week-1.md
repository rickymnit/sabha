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

## P1.5 · Identity and roles

> **Status (2026-10-17).** Already built (P1.5a): Auth0 token validation, `current_principal` / `require_role`, web AuthProvider, ProtectedRoute and sign-out, ADR 0002, `docs/setup/auth.md`. Remaining (P1.5b): look up users through the `identities` collection, `POST /v1/users/invites`, `GET /v1/me`. Needs an Auth0 dev tenant for the "Done when".

Plan task 1.5. Read first: `docs/adr/` (write 0002-auth.md as part of this task).

```text
Add authentication and roles. We use an external OIDC provider (Auth0 or Keycloak — write
docs/adr/0002-auth.md comparing them in 10 lines and recommend one for a solo engineer; I will confirm).

API:
- auth/oidc.py: validate JWT access tokens against the issuer's JWKS (cached), audience and expiry.
- Map token claims to an internal user: look up users by (issuer, subject); first login creates nothing
  unless an admin has invited that email (invite flow: POST /v1/users/invites by owner/admin).
- Roles: owner, admin, manager, reviewer, staff. A dependency `require_role(...)` and `current_principal`
  returning user_id, tenant_id, role, unit_ids.
- GET /v1/me returns the principal and the tenant's labels.
Web:
- Login with the provider's SPA SDK (PKCE), token refresh, logout; an AuthProvider and a ProtectedRoute.

Tests: expired token 401, wrong audience 401, staff hitting an admin route 403, uninvited user 403.
Out of scope: SSO configuration in the provider console (document the steps in docs/setup/auth.md instead).
```

Done when: you log in with Google on dev and `/v1/me` returns your role and tenant.

---

## P1.6 · Tenant model and tenant-scoped repository

> **Status (2026-10-17).** Already built, not yet committed: `models.py`, `repo.py` (TenantRepo, SyncTenantRepo, SystemRepo), `indexes.py`, the isolation and lint tests (all pass). Remaining: fix /tenant-check findings 1 (per-user rate-limit key without tenant) and 2 (duplicate-key id oracle: test plus no-client-ids rule); the API dependency that builds TenantRepo from the principal; commit.

Plan task 1.6. **Write the tests first.** Read first: `CLAUDE.md` golden rule 1.

```text
Implement tenancy. Write the tests first and show them to me before the implementation.

packages/core/sabha_core/:
- models.py: Pydantic models for Tenant (name, profile school|college|company, enabled_types, labels dict,
  plan, retention_days, region, kms_key_id), Unit (tree via parent_id), User, Person.
- repo.py: TenantRepo[T] bound to (db, collection, tenant_id). Every find/insert/update/delete/aggregate
  injects tenant_id; insert sets it; update cannot change it; aggregate prepends a $match on tenant_id.
  Constructing it without a tenant_id raises. A separate SystemRepo exists only for tenants and outbox,
  and is importable only from apps/workers/relay.py and admin scripts (enforce with a lint test).
- indexes.py: creates all indexes listed in CLAUDE.md's domain model, idempotently, at startup.
API: dependency that builds TenantRepo instances from the current principal's tenant_id.

Tests (tests/security/test_tenant_isolation.py): two tenants with data; tenant A cannot read, update,
delete or aggregate tenant B's documents through any repo method; a raw collection import outside allowed
modules fails the lint test.
```

Done when: the isolation tests pass and `/tenant-check` reports no findings.

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
