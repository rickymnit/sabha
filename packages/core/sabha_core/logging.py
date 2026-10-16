"""Structured JSON logging shared by the API and the workers.

Every record is one JSON object per line with `ts`, `level`, `logger`, `message`, the current `request_id` and
`tenant_id` (from context variables, set per request or per task) and, inside a traced request, `trace_id`.
Fields passed with `extra=` are included.

Secrets are never logged:
- an `extra` field whose name looks like a secret (password, token, api key, authorization, cookie, ...) is masked,
  at any depth;
- `SecretStr` values print masked;
- `user:password@` in any URL, in the message or in a field, is masked.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import IO, Any

from opentelemetry import trace
from pydantic import SecretStr

MASK = "**********"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)

_SECRET_NAME = re.compile(
    r"(?i)(password|passwd|secret|token|api_?key|access_?key|private_?key|authorization|cookie|credential|dsn)"
)
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]*:)[^@\s/]*@")

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def scrub(value: Any, key: str | None = None) -> Any:
    """`value` with secrets masked (module docstring); `key` is the field name it is stored under."""
    if key is not None and _SECRET_NAME.search(key):
        return MASK
    if isinstance(value, SecretStr):
        return MASK
    if isinstance(value, str):
        return _URL_CREDENTIALS.sub(rf"\1{MASK}@", value)
    if isinstance(value, dict):
        return {str(k): scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [scrub(v) for v in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return scrub(str(value))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub(record.getMessage()),
            "request_id": request_id_var.get(),
            "tenant_id": tenant_id_var.get(),
        }
        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            entry["trace_id"] = format(span.trace_id, "032x")
        for name, value in vars(record).items():
            if name not in _STANDARD_ATTRS and name not in entry and not name.startswith("_"):
                entry[name] = scrub(value, name)
        if record.exc_info:
            entry["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", *, stream: IO[str] | None = None) -> None:
    """Send every log record, ours and the libraries', through one JSON handler on the root logger."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    # The API writes its own access log line (sabha_api.middleware); uvicorn's would log raw query strings.
    logging.getLogger("uvicorn.access").disabled = True


@contextmanager
def log_context(*, request_id: str | None = None, tenant_id: str | None = None) -> Iterator[None]:
    """Set `request_id` / `tenant_id` for the records logged inside the block, then restore the previous values."""
    tokens = []
    if request_id is not None:
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if tenant_id is not None:
        tokens.append((tenant_id_var, tenant_id_var.set(tenant_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
