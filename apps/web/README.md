# apps/web

The React 18 + TypeScript + Vite single-page app used by school staff and admins. Design tokens and shared components live in `src/design/`; Tailwind is configured from `docs/design/tokens.md`. UI words come from the tenant's `labels` dictionary, never hard-coded, and times are shown in Asia/Kolkata. The overview design spike is in `src/spike/`, the component demo is at `/dev/components` and the transcript player demo (P6.5, mock data and synthesised audio) at `/dev/transcript` (dev server only). The transcript view lives in `src/features/transcript/`; its types mirror `packages/asr/sabha_asr/schemas/transcript.v1.schema.json`. Run it with `pnpm -C apps/web dev`.

## Run the whole product locally (dev sign-in)

Until Auth0 is set up (last), the app signs in through the API's local dev sign-in (`sabha_api/auth/dev_idp.py`,
APP_ENV=local only):

1. In the repo's `.env`: `APP_ENV=local`, `DEV_LOGIN=true`, `OIDC_ISSUER=http://localhost:8000/dev-idp`,
   `OIDC_AUDIENCE=sabha-local`, `OIDC_CLIENT_ID=sabha-web`, `CORS_ORIGINS=http://localhost:5173` (storage CORS for
   direct uploads).
2. `make dev` (MongoDB, Redis, RustFS and the buckets), then `uv run python scripts/admin/dev_seed.py` once.
3. `make api`, `make workers` and `make relay` in three terminals (the pipeline needs `make models`, and
   `make setup-speech` for diarization).
4. In `apps/web/.env.local`: `VITE_AUTH_MODE=dev`; then `pnpm -C apps/web dev` and open http://localhost:5173.
   Pick someone on the sign-in page. Vite forwards `/v1` and `/dev-idp` to the API on port 8000.

Pages today: recordings (status refreshes while processing), a recording's report and transcript with playback,
and upload (one file, up to 512 MB; resuming after a reload and hashing in a worker come with the rest of P6.3).

## Audit exceptions

`package.json` → `pnpm.auditConfig.ignoreGhsas` skips advisories that CI's `pnpm audit --audit-level=high` would otherwise fail on. Each one must be listed here with its reason, and removed once a fix exists.

| Advisory                                                                 | Package and path                        | Why it is ignored                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | `braces` via `tailwindcss` → `chokidar` | No patched version exists. It is a build-time dependency of Tailwind 3's file watcher and never ships to browsers; the attack needs untrusted glob patterns, and ours come from our own config. Goes away when we move to Tailwind 4. |
