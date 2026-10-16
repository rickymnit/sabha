"""Liveness, readiness and build metadata. No authentication: load balancers and the deploy script call these.

- GET /health: the process is up. Never touches a dependency, so a slow database cannot get the API restarted.
- GET /ready: MongoDB, Redis and object storage all answer within READY_TIMEOUT_S; otherwise 503 problem+json
  (code `not_ready`) naming the failed dependencies. Dependency error text is logged by type only, never returned.
- GET /v1/meta: version, git commit and environment.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sabha_api.errors import NotReadyError
from sabha_api.resources import Check, Resources
from sabha_core.settings import Settings
from sabha_core.telemetry import package_version

READY_TIMEOUT_S = 2.0

router = APIRouter(tags=["health"])
log = logging.getLogger("sabha.api.health")

CheckState = Literal["ok", "failed", "timeout"]


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]
    checks: dict[str, CheckState]


class Meta(BaseModel):
    version: str
    git_sha: str | None
    env: str


@router.get("/health")
async def health() -> Health:
    return Health(status="ok")


async def _run(name: str, check: Check) -> CheckState:
    try:
        await asyncio.wait_for(check(), READY_TIMEOUT_S)
    except TimeoutError:
        log.warning("readiness check timed out", extra={"check": name})
        return "timeout"
    except Exception as exc:  # any failure means not ready
        log.warning("readiness check failed", extra={"check": name, "error_type": type(exc).__name__})
        return "failed"
    return "ok"


@router.get("/ready", responses={503: {"description": "A dependency is unavailable (code `not_ready`)"}})
async def ready(request: Request) -> Ready:
    resources: Resources = request.app.state.resources
    names = list(resources.readiness)
    states = await asyncio.gather(*(_run(n, resources.readiness[n]) for n in names))
    checks = dict(zip(names, states, strict=True))
    failed = [name for name, state in checks.items() if state != "ok"]
    if failed:
        raise NotReadyError(f"Unavailable: {', '.join(failed)}.", extra={"checks": checks})
    return Ready(status="ready", checks=checks)


@router.get("/v1/meta")
async def meta(request: Request) -> Meta:
    settings: Settings = request.app.state.settings
    return Meta(version=package_version("sabha-api"), git_sha=settings.git_sha, env=settings.app_env)
