# apps/web

The React 18 + TypeScript + Vite single-page app used by school staff and admins. Design tokens and shared components live in `src/design/`; Tailwind is configured from `docs/design/tokens.md`. UI words come from the tenant's `labels` dictionary, never hard-coded, and times are shown in Asia/Kolkata. The overview design spike is in `src/spike/`, the component demo is at `/dev/components` and the transcript player demo (P6.5, mock data and synthesised audio) at `/dev/transcript` (dev server only). The transcript view lives in `src/features/transcript/`; its types mirror `packages/asr/sabha_asr/schemas/transcript.v1.schema.json`. Run it with `pnpm -C apps/web dev`.

## Run the whole product locally (dev sign-in)

Until Auth0 is set up (last), the app signs in through the API's local dev sign-in (`sabha_api/auth/dev_idp.py`,
APP_ENV=local only):

1. In the repo's `.env`: `APP_ENV=local`, `DEV_LOGIN=true`, `OIDC_ISSUER=http://localhost:8000/dev-idp`,
   `OIDC_AUDIENCE=sabha-local`, `OIDC_CLIENT_ID=sabha-web`, `CORS_ORIGINS=http://localhost:5180` (storage CORS for
   direct uploads).
2. `make dev` (MongoDB, Redis, RustFS and the buckets), then `uv run python scripts/admin/dev_seed.py` once.
3. `make api`, `make workers` and `make relay` in three terminals (the pipeline needs `make models`, and
   `make setup-speech` for diarization).
4. In `apps/web/.env.local`: `VITE_AUTH_MODE=dev`; then `pnpm -C apps/web dev` and open http://localhost:5180.
   Pick someone on the sign-in page. Vite forwards `/v1` and `/dev-idp` to the API on port 8000.

Pages today (only finished pages are in the menu, `src/app/nav.ts`): Overview (owners, admins, managers,
reviewers; it is their home page), recordings (filters by type and person; status refreshes while processing), a
recording's report and transcript with playback, people with their trend, and upload (several files, up to 512 MB
each; resuming after a reload and hashing in a worker come with the rest of P6.3).

## Browser smoke tests (Playwright)

`make e2e` runs `e2e/*.e2e.ts` in Chromium at desktop (1440 px) and phone (Pixel 7) widths against the running
stack above (it reseeds first and starts the web dev server if it is not running). Reading tests use the demo
school's accounts and change nothing; the upload test signs in to the hidden "E2E School" (`dev_seed.py`; not on
the sign-in page), so test files never appear in the demo. First time only: `pnpm -C apps/web exec playwright
install chromium`. On failure, the screenshot and trace are in `apps/web/test-results/`.

## Audit exceptions

`package.json` → `pnpm.auditConfig.ignoreGhsas` skips advisories that CI's `pnpm audit --audit-level=high` would otherwise fail on. Each one must be listed here with its reason, and removed once a fix exists.

| Advisory                                                                                                                                                                                                                     | Package and path                        | Why it is ignored                                                                                                                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)                                                                                                                                                     | `braces` via `tailwindcss` → `chokidar` | No patched version exists. It is a build-time dependency of Tailwind 3's file watcher and never ships to browsers; the attack needs untrusted glob patterns, and ours come from our own config. Goes away when we move to Tailwind 4.                                                                     |
| [GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c)                                                                                                                                                     | `undici` 8.x via `jsdom`                | Unit-test DOM only; never ships to browsers. The fix (undici 8.12.2, published 2026-10-15) is younger than our 14-day install rule. **Remove on or after 2026-10-29** and update undici.                                                                                                                  |
| [GHSA-4w7w-5xrc-9h26](https://github.com/advisories/GHSA-4w7w-5xrc-9h26), [GHSA-2m5v-pch6-74hx](https://github.com/advisories/GHSA-2m5v-pch6-74hx), [GHSA-qrxm-fqhp-jwvm](https://github.com/advisories/GHSA-qrxm-fqhp-jwvm) | `undici` 8.x via `jsdom`                | Same package and fix as the row above (undici 8.12.2; jsdom 30.1.3 asks for it), published 2026-10-15, younger than the 14-day install rule. Unit-test DOM only; tests make no TLS connections to untrusted servers. **Remove on or after 2026-10-29** (from about 15:05 UTC) and update jsdom to 30.1.3. |
