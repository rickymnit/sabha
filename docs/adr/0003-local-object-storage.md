# ADR 0003: RustFS for local object storage

- **Status:** Accepted
- **Date:** 2026-10-14
- **Plan task:** 1.1

## Context

`CLAUDE.md` and ADR 0001 chose MinIO as the S3-compatible store for local development; staging and production use
AWS S3 in `ap-south-1`. When P1.1 set up `infra/docker-compose.dev.yml`, MinIO images no longer existed:

- `docker manifest inspect` found no `minio/minio` or `minio/mc` tags on Docker Hub (the repository returns
  "object not found") and none on `quay.io/minio/*`.
- The last MinIO GitHub release was `RELEASE.2025-10-15T17-29-55Z`, a year before this decision.

Building an unmaintained server from source for every developer was not attractive, so we compared maintained,
Apache-2.0 alternatives against what Sabha needs from S3 (P2.1 and P2.2 uploads, P1.3 lifecycle tags).

## What we tested

A probe script ran the same operations against each candidate:

| Check | RustFS 1.0.0 | SeaweedFS 4.48 |
| --- | --- | --- |
| Create the three buckets | pass | pass |
| Put, get, delete | pass | pass |
| Object tagging (`data-class=audio`) | pass | pass |
| Wrong secret rejected | pass | pass |
| Bucket CORS stored | pass | pass |
| Presigned multipart upload of two parts, tags kept, `ETag` exposed on PUT | pass | pass |
| CORS preflight allowed for the web origin | pass | pass |
| CORS preflight refused for another origin | pass | pass |
| Image size | 401 MB | 724 MB |
| Idle memory | about 160 MB | about 182 MB |

LocalStack's repository is archived; Garage is AGPL-3.0 and needs more configuration.

## Decision

Use **RustFS** (`rustfs/rustfs:1.0.0`) locally. It is built as a MinIO replacement, has the same access-key
model and a web console, and is the lighter of the two, which matters on developer machines with little RAM.
Buckets and CORS rules are created by `scripts/dev_storage.py`, which `make dev` runs (the MinIO `mc` image is
gone too).

## Consequences

- Nothing changes for staging and production: they use AWS S3, and the app refuses `S3_ENDPOINT_URL` there.
- Application code only uses the S3 API through boto3, so switching to SeaweedFS later means changing the image
  and start-up command in `infra/docker-compose.dev.yml`, not code.
- RustFS 1.0 is young. If a behaviour differs from S3, the AWS behaviour wins; record the gap and test it
  against staging.
