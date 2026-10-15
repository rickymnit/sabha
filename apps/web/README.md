# apps/web

The React 18 + TypeScript + Vite single-page app used by school staff and admins. Design tokens and shared components live in `src/design/`; Tailwind is configured from `docs/design/tokens.md`. UI words come from the tenant's `labels` dictionary, never hard-coded, and times are shown in Asia/Kolkata. The overview design spike is in `src/spike/`, and the component demo is at `/dev/components` (dev server only). Run it with `pnpm -C apps/web dev`.

## Audit exceptions

`package.json` → `pnpm.auditConfig.ignoreGhsas` skips advisories that CI's `pnpm audit --audit-level=high` would otherwise fail on. Each one must be listed here with its reason, and removed once a fix exists.

| Advisory                                                                 | Package and path                        | Why it is ignored                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | `braces` via `tailwindcss` → `chokidar` | No patched version exists. It is a build-time dependency of Tailwind 3's file watcher and never ships to browsers; the attack needs untrusted glob patterns, and ours come from our own config. Goes away when we move to Tailwind 4. |
