# API image (plan task P1.2). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t sabha-api .

FROM python:3.12.15-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Dependencies first, so source edits do not invalidate this layer. The lock file needs every member's pyproject.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY packages/asr/pyproject.toml packages/asr/
COPY packages/llm/pyproject.toml packages/llm/
COPY packages/analytics/pyproject.toml packages/analytics/
COPY apps/api/pyproject.toml apps/api/
COPY apps/workers/pyproject.toml apps/workers/
RUN uv sync --frozen --no-dev --package sabha-api --no-install-workspace
COPY packages packages
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package sabha-api --no-editable

FROM python:3.12.15-slim-bookworm
RUN groupadd --system --gid 10001 sabha && useradd --system --uid 10001 --gid sabha --no-create-home sabha
COPY --from=build --chown=sabha:sabha /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER sabha
EXPOSE 8000
# sabha_api.main arrives with plan task P1.4.
CMD ["uvicorn", "sabha_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
