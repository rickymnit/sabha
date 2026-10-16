# apps/api

The FastAPI service that the web app and integrations talk to. It holds the versioned `/v1` routers, request and response schemas, OIDC token validation, and thin services that call the tenant-scoped repository in `packages/core`. It authorises uploads and records intent but never touches audio bytes: clients upload straight to object storage with presigned multipart URLs. Errors are RFC 9457 problem+json, every create honours `Idempotency-Key`, and pagination is cursor-based.

## Run it

```
make dev    # Mongo, Redis and RustFS
make api    # http://localhost:8000, reloads on save; needs OIDC_* in .env (P1.5)
```

- `GET /health`: the process is up (never checks a dependency).
- `GET /ready`: Mongo, Redis and both storage buckets answer within 2 s, otherwise 503 `not_ready` naming them.
- `GET /v1/meta`: version, git commit (`GIT_SHA`) and environment.
- `/docs`: OpenAPI, served everywhere except production.

Every response carries `X-Request-Id` (yours if it is 1-128 characters of `[A-Za-z0-9._-]`, otherwise a new one);
the same id is in every log line for the request and in every error body. Errors are `application/problem+json`
with a stable `code` (`sabha_api/errors.py`). Logs are JSON on stdout with secrets masked (`sabha_core/logging.py`);
tracing is on when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (`sabha_core/telemetry.py`).
