"""Errors as RFC 9457 problem details (CLAUDE.md, API conventions).

Every error response is `application/problem+json`:

    {"type": "urn:sabha:problem:<code>", "title": ..., "status": ..., "detail": ..., "code": ..., "request_id": ...}

`code` is stable: clients branch on it, never on `title` or `detail`. Raise an `ApiError` subclass from services and
routers; FastAPI's own errors (404 for an unknown path, 405, 422 validation) are mapped to the same shape here, and
unexpected exceptions become a generic 500 in sabha_api.middleware without leaking their text.
"""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException

from sabha_core.logging import request_id_var

PROBLEM_MEDIA_TYPE = "application/problem+json"


class Problem(BaseModel):
    """An RFC 9457 problem detail. Some codes add members (validation errors list `errors`)."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {
        "description": "Error, as RFC 9457 problem details",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }
}
"""OpenAPI `responses` entry for every route; replaces FastAPI's default 422 schema (sabha_api.main adds Problem)."""


class ApiError(Exception):
    """Base class for errors the API returns on purpose. Subclasses fix `status`, `code` and `title`."""

    status: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    title: ClassVar[str] = "Internal error"

    def __init__(
        self, detail: str, *, headers: Mapping[str, str] | None = None, extra: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = dict(headers or {})
        self.extra = dict(extra or {})


class BadRequestError(ApiError):
    status, code, title = 400, "bad_request", "Bad request"


class UnauthorizedError(ApiError):
    status, code, title = 401, "unauthorized", "Not signed in"


class ForbiddenError(ApiError):
    status, code, title = 403, "forbidden", "Not allowed"


class NotFoundError(ApiError):
    status, code, title = 404, "not_found", "Not found"


class ConflictError(ApiError):
    status, code, title = 409, "conflict", "Conflict"


class NotReadyError(ApiError):
    status, code, title = 503, "not_ready", "Not ready"


# FastAPI/Starlette HTTP errors that reach us without an ApiError, by status.
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def problem_response(
    status: int,
    code: str,
    title: str,
    detail: str,
    *,
    headers: Mapping[str, str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> JSONResponse:
    body = {
        **(extra or {}),
        "type": f"urn:sabha:problem:{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": request_id_var.get(),
    }
    return JSONResponse(body, status_code=status, headers=dict(headers or {}), media_type=PROBLEM_MEDIA_TYPE)


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101  # registered for ApiError only
    return problem_response(exc.status, exc.code, exc.title, exc.detail, headers=exc.headers, extra=exc.extra)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)  # noqa: S101  # registered for HTTPException only
    phrase = HTTPStatus(exc.status_code).phrase
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else phrase
    code = _HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
    return problem_response(exc.status_code, code, phrase, detail, headers=exc.headers)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101  # registered for RequestValidationError only
    # Field locations and messages only: the submitted values may be personal data or secrets.
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return problem_response(
        422, "validation_error", "Invalid request", "The request is not valid.", extra={"errors": errors}
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
