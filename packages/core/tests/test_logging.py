"""JSON logs carry request and tenant ids and never contain secrets."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr

from sabha_core.logging import MASK, configure_logging, log_context, scrub


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    out = io.StringIO()
    configure_logging("DEBUG", stream=out)
    yield out
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_one_json_object_per_record_with_context(stream: io.StringIO) -> None:
    log = logging.getLogger("sabha.test")
    with log_context(request_id="req-1", tenant_id="t-1"):
        log.info("hello %s", "world", extra={"recording_id": "rec-9"})
    log.info("outside")
    first, second = lines(stream)
    assert first["message"] == "hello world"
    assert first["level"] == "INFO"
    assert first["logger"] == "sabha.test"
    assert (first["request_id"], first["tenant_id"], first["recording_id"]) == ("req-1", "t-1", "rec-9")
    assert (second["request_id"], second["tenant_id"]) == (None, None)


def test_context_is_restored_after_nested_blocks(stream: io.StringIO) -> None:
    log = logging.getLogger("sabha.test")
    with log_context(request_id="outer"):
        with log_context(tenant_id="t-2"):
            log.info("inner")
        log.info("after")
    inner, after = lines(stream)
    assert (inner["request_id"], inner["tenant_id"]) == ("outer", "t-2")
    assert (after["request_id"], after["tenant_id"]) == ("outer", None)


SECRET = "hunter2-do-not-leak"  # pragma: allowlist secret  (fake test value)


def test_secret_looking_fields_are_masked_at_any_depth(stream: io.StringIO) -> None:
    logging.getLogger("sabha.test").info(
        "calling provider",
        extra={
            "api_key": SECRET,
            "headers": {"Authorization": f"Bearer {SECRET}", "Accept": "application/json"},
            "settings": {"mongo": {"password": SECRET}},
            "idempotency": "k-1",
        },
    )
    [entry] = lines(stream)
    assert SECRET not in stream.getvalue()
    assert entry["api_key"] == MASK
    assert entry["headers"] == {"Authorization": MASK, "Accept": "application/json"}
    assert entry["settings"] == {"mongo": {"password": MASK}}
    assert entry["idempotency"] == "k-1"


def test_secret_str_and_url_credentials_are_masked(stream: io.StringIO) -> None:
    log = logging.getLogger("sabha.test")
    log.info("connecting to mongodb://sabha:%s@db:27017/?replicaSet=rs0", SECRET, extra={"value": SecretStr(SECRET)})
    log.info("redis", extra={"target": f"redis://:{SECRET}@cache:6379/0"})
    assert SECRET not in stream.getvalue()
    first, second = lines(stream)
    assert first["message"] == f"connecting to mongodb://sabha:{MASK}@db:27017/?replicaSet=rs0"
    assert first["value"] == MASK
    assert second["target"] == f"redis://:{MASK}@cache:6379/0"


def test_tracebacks_are_scrubbed_too(stream: io.StringIO) -> None:
    try:
        raise ConnectionError(f"mongodb://u:{SECRET}@db refused")
    except ConnectionError:
        logging.getLogger("sabha.test").exception("failed")
    [entry] = lines(stream)
    assert "ConnectionError" in entry["exc"]
    assert SECRET not in stream.getvalue()


def test_scrub_leaves_ordinary_values_alone() -> None:
    assert scrub({"count": 3, "ok": True, "ratio": 0.5, "none": None, "ids": ("a", "b")}) == {
        "count": 3,
        "ok": True,
        "ratio": 0.5,
        "none": None,
        "ids": ["a", "b"],
    }
    assert scrub("https://example.com/path?x=1") == "https://example.com/path?x=1"


def test_uvicorn_access_log_is_off_and_library_logs_reach_the_json_handler(stream: io.StringIO) -> None:
    assert logging.getLogger("uvicorn.access").disabled
    logging.getLogger("uvicorn.error").warning("from uvicorn")
    assert lines(stream)[0]["logger"] == "uvicorn.error"
