"""Request context middleware: request id, access log, security headers and the last-resort 500.

It is the outermost middleware, so every response, errors and CORS preflights included, gets:
- `X-Request-Id`: the caller's value if it is 1-128 characters of [A-Za-z0-9._-], otherwise a new id. The id is
  also in the logging context for the whole request and in every problem+json body.
- security headers (below); HSTS only where TLS is in front of us (staging, production).
- one JSON access-log line: method, route template (never the raw path or query string), status, duration.

An exception that nothing else handled is logged with its traceback and answered with a generic problem+json 500,
so its text never reaches the client.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sabha_api.errors import problem_response
from sabha_core.logging import log_context

REQUEST_ID_HEADER = "X-Request-Id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
# Health probes run every few seconds; their access lines are DEBUG so they do not drown the log.
_QUIET_ROUTES = frozenset({"/health", "/ready"})
# Swagger UI needs scripts and styles from its CDN; it exists only outside production (sabha_api.main).
_DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect"})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}
HSTS = "max-age=31536000; includeSubDomains"

access_log = logging.getLogger("sabha.access")
error_log = logging.getLogger("sabha.api")


def request_id_from(header: str | None) -> str:
    if header is not None and _VALID_REQUEST_ID.match(header):
        return header
    return uuid.uuid4().hex


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), None)
        request_id = request_id_from(incoming)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status, response_started = message["status"], True
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS.items():
                    if name == "Content-Security-Policy" and scope["path"] in _DOCS_PATHS:
                        continue
                    headers.setdefault(name, value)
                if self.hsts:
                    headers["Strict-Transport-Security"] = HSTS
            await send(message)

        with log_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_headers)
            except Exception:
                error_log.exception("unhandled error")
                if response_started:
                    raise  # too late for a problem response; the server closes the connection
                response = problem_response(
                    500, "internal_error", "Internal error", "Something went wrong on our side."
                )
                await response(scope, receive, send_with_headers)
            finally:
                # The route template keeps ids out of the log. FastAPI's own pages (/docs) carry no template but
                # have fixed paths; anything unmatched is not logged by path at all.
                template = getattr(scope.get("route"), "path", None)
                if template is None and "endpoint" in scope:
                    template = scope["path"]
                access_log.log(
                    logging.DEBUG if template in _QUIET_ROUTES else logging.INFO,
                    "request",
                    extra={
                        "method": scope["method"],
                        "route": template or "<unmatched>",
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
