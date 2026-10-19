# Security findings (plan task P7.6)

One row per finding, kept up to date: severity, status and the fix (commit) or the reason it is accepted. "Done
when" for P7.6 is that no high-severity finding is open. Checks that need staging (OWASP ZAP baseline scan, S3
bucket policies, IAM, trivy on published images) are listed under "Not run yet" until they have been run; no
result is recorded for a check that did not run.

## Findings

| # | Date | Check | Finding | Severity | Status | Fix or reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-19 | `pip-audit` (all Python dependencies from `uv.lock`) | No known vulnerabilities | none | closed | None needed |
| 2 | 2026-10-19 | `pnpm audit` (apps/web) | [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm): `braces` via `tailwindcss` -> `chokidar` | high | accepted | No patched version exists; build-time only, inputs are our own config. Recorded in `apps/web/README.md`; goes away with Tailwind 4 |
| 3 | 2026-10-19 | `pnpm audit` (apps/web) | [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf): `postcss-selector-parser` 6.1.4 via `tailwindcss` (CPU exhaustion on hostile selectors) | moderate | accepted | Fixed only in 7.1.6, which Tailwind 3 (`^6.1.2`) cannot use. Build-time only: it parses our own CSS, never user input, and never ships to browsers. Goes away with Tailwind 4 |
| 4 | 2026-10-17 | `/tenant-check` | Per-user rate-limit key without tenant | low | fixed | 4656949 (P1.6) |
| 5 | 2026-10-17 | `/tenant-check` | Duplicate-key error reveals that an id exists in another tenant | low | fixed | Rule: ids are server-generated, clients cannot send them; test in `tests/security` (P1.6, P1.5b, P2.1) |
| 6 | 2026-10-17 | `/tenant-check` | Email delivery keys without tenant | low | fixed | 17b60cf: `deliveries` unique per (tenant, key) (P2.7) |

## Reviewed in code (no finding)

| Area | Where | Note |
| --- | --- | --- |
| JWT validation | `apps/api/sabha_api/auth/oidc.py` | RS256 only, issuer, audience, expiry, key rotation; algorithm-confusion and unsigned tokens refused (tests) |
| Tenant isolation | `packages/core/sabha_core/repo.py`, `tests/security/` | Every route checked as nine callers against `permissions.yaml` |
| Presigned URLs | `apps/api/sabha_api/services/recordings.py` | Upload parts only, 15-minute expiry, keys always under `{tenant_id}/` |
| Error messages | `apps/api/sabha_api/errors.py` | problem+json; unexpected errors become a generic 500 without internals |

## Not run yet

| Check | Needs |
| --- | --- |
| OWASP ZAP baseline scan (authenticated) | Staging (P1.3) |
| trivy on the published images | The CI `images` job switched on (`PUBLISH_IMAGES`) |
| S3 bucket policies, IAM least privilege | The AWS account and Terraform (P1.3) |
| SSRF guard for webhook URLs | Webhooks (P2.7, not built yet) |
| ffmpeg `-protocol_whitelist file` | The preprocess stage (P3.2, not built yet) |
| Secrets rotation procedure | The runbook (P7.7) |
