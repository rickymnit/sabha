# Developer commands. Run `make help` for the list.
# Python goes through uv, the web app through pnpm, local services through Docker Compose.

SHELL := /bin/bash
# uv's installer puts it in ~/.local/bin, which non-login shells (some IDE terminals, CI) may not have on PATH.
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
PNPM ?= pnpm
COMPOSE := docker compose --env-file .env -f infra/docker-compose.dev.yml -p sabha-dev
PY_STRICT := packages/core packages/asr packages/llm packages/analytics eval/goldset
PY_APPS := apps/api apps/workers scripts
MYPY := $(UV) run mypy --config-file $(CURDIR)/pyproject.toml

.DEFAULT_GOAL := help
.PHONY: help env setup dev down logs test test-py test-web test-fast lint lint-py lint-web fmt e2e eval-wer eval-kappa

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example with random local RustFS credentials (never overwrites)
	@if [ -f .env ]; then echo ".env already exists; leaving it alone"; else \
		cp .env.example .env && \
		sed -i "s|^S3_ACCESS_KEY_ID=$$|S3_ACCESS_KEY_ID=dev-$$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')|; \
		        s|^S3_SECRET_ACCESS_KEY=$$|S3_SECRET_ACCESS_KEY=$$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')|" .env && \
		chmod 600 .env && echo "created .env (fill in OIDC_* when P1.5 lands)"; fi

setup: env ## Install Python and web dependencies and the git hooks
	$(UV) sync
	$(PNPM) -C apps/web install
	$(UV) run pre-commit install

dev: env ## Start Mongo (replica set), Redis and RustFS, then create the buckets
	$(COMPOSE) up -d --wait
	$(UV) run python scripts/dev_storage.py
	@echo "Services up. Web app: pnpm -C apps/web dev (API and workers arrive in P1.4/P2.4)."

down: ## Stop local services (data volumes are kept)
	$(COMPOSE) down

logs: ## Follow local service logs
	$(COMPOSE) logs -f

test: test-py test-web ## All Python tests (integration tests start containers) and web unit tests

test-py: ## Python tests with a coverage report in coverage.xml
	$(UV) run pytest --cov=packages --cov=apps --cov=scripts --cov=eval --cov-report=term --cov-report=xml

test-web: ## Web unit tests
	$(PNPM) -C apps/web test

test-fast: ## Tests that need no Docker
	$(UV) run pytest -m "not integration"
	$(PNPM) -C apps/web test

lint: lint-py lint-web ## ruff, mypy (strict on packages/), eslint, prettier and tsc

lint-py: ## ruff and mypy
	$(UV) run ruff check
	$(UV) run ruff format --check
	@set -e; for p in $(PY_STRICT); do echo "mypy --strict $$p"; (cd $$p && $(MYPY) --strict .); done
	@set -e; for p in $(PY_APPS); do echo "mypy $$p"; (cd $$p && $(MYPY) .); done
	@echo "mypy --strict eval"; cd eval && MYPYPATH=goldset $(MYPY) --strict *.py tests

lint-web: ## eslint, prettier and tsc
	$(PNPM) -C apps/web lint
	$(PNPM) -C apps/web format:check
	$(PNPM) -C apps/web typecheck

fmt: ## Fix formatting and autofixable lint
	$(UV) run ruff check --fix
	$(UV) run ruff format
	$(PNPM) -C apps/web format

e2e: ## Playwright against the dev stack
	@echo "e2e: not implemented yet (P6.2)"

eval-wer: ## WER and role accuracy on the hold-out set: make eval-wer HYP_DIR=<dir of transcript@v1 files>
	@test -n "$(HYP_DIR)" || { echo "set HYP_DIR to a folder of system transcripts (<recording_id>.json)"; exit 2; }
	$(UV) run python eval/wer.py --hyp-dir $(HYP_DIR); wer=$$?; \
	$(UV) run python eval/roles.py --hyp-dir $(HYP_DIR); roles=$$?; \
	exit $$(( wer > roles ? wer : roles ))

eval-kappa: ## eval/kappa.py on the calibration hold-out split
	@echo "eval-kappa: not implemented yet (P4.6)"
