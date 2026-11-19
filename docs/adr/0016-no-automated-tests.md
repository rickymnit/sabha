# ADR 0016: Automated tests removed

- **Status:** Accepted
- **Date:** 2026-11-19

## Context

The repo had about 190 test files: pytest suites in every package and app (integration tests ran MongoDB, Redis
and S3 in Docker through testcontainers), cross-package security tests (tenant isolation, raw collection access,
the permission matrix for every route), web unit tests (Vitest) and Playwright browser tests. With no CI
([ADR 0010](0010-no-github-actions.md)) they ran only by hand.

On 2026-11-19 the owner decided to delete all test files, after being told this goes against the rule in
`CLAUDE.md` that every change carries tests.

## Decision

- All test files are deleted, with `conftest.py`, the Playwright config and the browser tests, and the developer
  demo pages under `apps/web/src/dev/`.
- `make test`, `make test-py`, `make test-web`, `make test-fast` and `make e2e` are gone, as are the pytest settings
  in `pyproject.toml` and the web test settings.
- The permission matrix stays, as a record of who may call which route: `docs/security/permissions.yaml`. Nothing
  enforces it any more; a new route needs its row added by hand.
- `make lint` (ruff, mypy, eslint, prettier, tsc) is the one automated check left.

## Consequences

- Nothing checks tenant isolation, grounding, idempotency, the state machine or permissions automatically. A
  change to any of them must be checked by hand in the running app.
- The test tools (pytest, testcontainers, Vitest, Playwright, jsdom) are still dev dependencies; removing them
  changes the lock files and is a separate step.
- All deleted tests are in git history (before commit `ad2408d`) and can be restored with `git checkout`.
