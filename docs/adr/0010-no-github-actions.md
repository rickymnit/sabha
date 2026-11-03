# ADR 0010: No GitHub Actions

- **Status:** Accepted
- **Date:** 2026-11-02
- **Supersedes:** the CI part of plan task P1.2 and the "GitHub Actions" row of ADR 0001

## Context

`.github/workflows/ci.yml` ran lint, tests and security audits on every pull request and push to `main`. The product
owner wants a plain repository on GitHub: pushes only, nothing in the Actions tab.

## Decision

Decided by the product owner on 2026-11-02. The workflow file is deleted and no other workflow is added. Before
pushing, developers run `make lint` and `make test` locally; pre-commit still runs detect-secrets on every commit.

## Consequences

- Nothing checks a push automatically. A broken test or lint error reaches `main` unless someone ran the checks.
- `pip-audit`, `pnpm audit` and gitleaks no longer run on their own; run them by hand when dependencies change.
- Image publishing to `ghcr.io` and the planned eval gate (P4.7) need another home if they are wanted later.
