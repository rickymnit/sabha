"""The API application factory.

Run locally with `make api`; in the image: `uvicorn sabha_api.main:create_app --factory`.

`create_app()` loads settings, configures JSON logging and tracing, and wires middleware and error handlers. The
lifespan opens one MongoDB, one Redis and one S3 client for the life of the process (sabha_api.resources).
OpenAPI and /docs are served only outside production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from sabha_api.auth import PrincipalStore, TokenVerifier, dev_idp
from sabha_api.auth.dev_idp import DevIdp
from sabha_api.auth.directory import Directory
from sabha_api.errors import PROBLEM_RESPONSES, Problem, install_error_handlers
from sabha_api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from sabha_api.resources import Resources, open_resources
from sabha_api.routers import (
    audit,
    disputes,
    erasure,
    events,
    health,
    me,
    overview,
    reanalysis,
    recordings,
    results,
    retry,
    reviews,
    rubrics,
    usage,
    users,
)
from sabha_api.routers import settings as workspace_settings
from sabha_core.logging import configure_logging
from sabha_core.settings import Settings, get_settings
from sabha_core.telemetry import package_version, setup_tracing

SERVICE_NAME = "sabha-api"

ResourcesFactory = Callable[[Settings], AbstractAsyncContextManager[Resources]]


def create_app(
    settings: Settings | None = None,
    *,
    resources: ResourcesFactory = open_resources,
    token_verifier: TokenVerifier | None = None,
    principals: PrincipalStore | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own `settings` and, to avoid real services, a `resources` factory, a
    `token_verifier` with a fake key fetcher and an in-memory `principals` store (sabha_api.auth)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    tracer_provider = setup_tracing(SERVICE_NAME, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with resources(settings) as opened:
            app.state.resources = opened
            if app.state.principals is None and opened.db is not None:
                app.state.directory = app.state.principals = Directory(opened.db, app.state.token_verifier)
            try:
                yield
            finally:
                if tracer_provider is not None:
                    tracer_provider.shutdown()

    docs = settings.app_env != "production"
    app = FastAPI(
        title="Sabha API",
        version=package_version(SERVICE_NAME),
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        responses=PROBLEM_RESPONSES,
    )
    app.state.settings = settings
    app.state.dev_idp = DevIdp(settings.oidc_issuer, settings.oidc_audience) if settings.dev_login else None
    default_verifier = (
        app.state.dev_idp.verifier()
        if app.state.dev_idp is not None
        else TokenVerifier(settings.oidc_issuer, settings.oidc_audience)
    )
    app.state.token_verifier = token_verifier or default_verifier
    # The MongoDB-backed directory is created with the resources (lifespan); tests may pass their own store.
    app.state.principals = principals
    app.state.directory = None
    install_error_handlers(app)
    app.include_router(health.router)
    if settings.dev_login:  # APP_ENV=local only (settings); not in the OpenAPI document
        app.include_router(dev_idp.router)
    app.include_router(me.router)
    app.include_router(users.router)
    app.include_router(recordings.router)
    app.include_router(results.recordings_router)
    app.include_router(results.people_router)
    app.include_router(overview.router)
    app.include_router(reviews.router)
    app.include_router(disputes.router)
    app.include_router(reanalysis.router)
    app.include_router(events.router)
    app.include_router(workspace_settings.router)
    app.include_router(usage.router)
    app.include_router(rubrics.router)
    app.include_router(audit.router)
    app.include_router(retry.router)
    app.include_router(erasure.router)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
            schema.setdefault("components", {}).setdefault("schemas", {})["Problem"] = problem
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented way to customise the schema

    # Added innermost first: the request context wraps everything, including CORS preflight answers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After", "WWW-Authenticate"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, hsts=settings.app_env in ("staging", "production"))
    if tracer_provider is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="/health,/ready")
    return app
