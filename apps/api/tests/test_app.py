"""Request ids, security headers, health endpoints, docs visibility and the access log."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sabha_api.middleware import request_id_from
from sabha_api.resources import open_resources
from sabha_api.routers import health

PRODUCTION = {"app_env": "production", "s3_endpoint_url": None}


async def ok() -> object:
    return None


async def down() -> object:
    raise ConnectionError("mongodb://admin:hunter2@db:27017 refused")  # pragma: allowlist secret  (fake test value)


def test_a_valid_request_id_is_kept(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-Id": "abc-123.x_y"})
    assert response.headers["x-request-id"] == "abc-123.x_y"


@pytest.mark.parametrize("bad", ["", "has space", "x" * 129, "a;drop"])
def test_an_unsafe_request_id_is_replaced(client: TestClient, bad: str) -> None:
    response = client.get("/health", headers={"X-Request-Id": bad})
    generated = response.headers["x-request-id"]
    assert generated != bad
    assert len(generated) == 32


def test_non_ascii_request_ids_are_replaced() -> None:
    # The test client cannot send non-ASCII header bytes, so this case checks the parser directly.
    assert request_id_from("badéid") != "badéid"


def test_each_request_without_an_id_gets_a_new_one(client: TestClient) -> None:
    first, second = client.get("/health"), client.get("/health")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_the_request_id_reaches_the_error_body(client: TestClient) -> None:
    response = client.get("/v1/missing", headers={"X-Request-Id": "trace-me"})
    assert response.json()["request_id"] == "trace-me"


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in headers  # no TLS in front of a test or local server


def test_hsts_in_production(make_client: Any) -> None:
    client = make_client(**PRODUCTION)
    assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")


def test_cors_allows_the_configured_origin_only(client: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "POST"}
    allowed = client.options("/v1/meta", headers={"Origin": "http://localhost:5173", **preflight})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in allowed.headers
    denied = client.options("/v1/meta", headers={"Origin": "https://evil.example.com", **preflight})
    assert "access-control-allow-origin" not in denied.headers


def test_health_needs_no_dependency(make_client: Any) -> None:
    client = make_client(checks={"mongo": down})
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_when_every_check_passes(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"mongo": "ok", "redis": "ok", "storage": "ok"}}


def test_ready_fails_when_mongo_is_down_without_leaking_the_error(make_client: Any) -> None:
    response = make_client(checks={"mongo": down, "redis": ok, "storage": ok}).get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "not_ready"
    assert body["detail"] == "Unavailable: mongo."
    assert body["checks"] == {"mongo": "failed", "redis": "ok", "storage": "ok"}
    assert "hunter2" not in response.text


def test_ready_reports_a_hanging_check_as_timeout(make_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang() -> object:
        await asyncio.sleep(5)
        return None

    monkeypatch.setattr(health, "READY_TIMEOUT_S", 0.05)
    response = make_client(checks={"mongo": ok, "redis": hang}).get("/ready")
    assert response.json()["checks"] == {"mongo": "ok", "redis": "timeout"}


def test_ready_with_real_clients_when_nothing_is_listening(make_client: Any) -> None:
    # The real resource factory against closed ports: every check must fail or time out, not hang or crash.
    client = make_client(
        resources=open_resources,
        mongo_uri="mongodb://127.0.0.1:1/?replicaSet=rs0&serverSelectionTimeoutMS=500",
        redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key_id="test",
        s3_secret_access_key="test",  # pragma: allowlist secret  (fake test value)
    )
    response = client.get("/ready")
    assert response.status_code == 503
    assert set(response.json()["checks"].values()) <= {"failed", "timeout"}


def test_meta(client: TestClient) -> None:
    body = client.get("/v1/meta").json()
    assert body == {"version": body["version"], "git_sha": "0123abc", "env": "test"}


def test_docs_are_hidden_in_production(make_client: Any) -> None:
    client = make_client(**PRODUCTION)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_are_served_outside_production(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers  # Swagger UI loads its assets from a CDN


def test_one_access_log_line_per_request_with_the_route_template(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="sabha.access"):
        client.get("/v1/meta?token=abc", headers={"X-Request-Id": "req-1"})
    [record] = [r for r in caplog.records if r.name == "sabha.access"]
    assert record.__dict__["route"] == "/v1/meta"
    assert record.__dict__["status"] == 200
    assert record.levelno == logging.INFO
    assert "token=abc" not in json.dumps({k: str(v) for k, v in record.__dict__.items()})


def test_health_probes_log_at_debug(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="sabha.access"):
        client.get("/health")
    [record] = [r for r in caplog.records if r.name == "sabha.access"]
    assert record.levelno == logging.DEBUG


def test_unmatched_paths_are_not_logged_by_path(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="sabha.access"):
        client.get("/v1/no-such-thing/9876543210")
        client.get("/docs")
    unmatched, docs = [r.__dict__["route"] for r in caplog.records if r.name == "sabha.access"]
    assert (unmatched, docs) == ("<unmatched>", "/docs")


@pytest.mark.integration
def test_indexes_are_created_in_the_background_and_reported_ready(
    make_client: Any, mongo_uri: str, mongo_replica_set: Any
) -> None:
    import time
    import uuid

    db_name = f"startup_{uuid.uuid4().hex[:12]}"
    client = make_client(
        resources=open_resources,
        mongo_uri=f"{mongo_uri}&replicaSet=rs0",
        mongo_db=db_name,
        redis_url="redis://127.0.0.1:1/0",
        s3_endpoint_url="http://127.0.0.1:1",
        s3_access_key_id="test",
        s3_secret_access_key="test",  # pragma: allowlist secret  (fake test value)
    )
    try:
        deadline = time.monotonic() + 30
        checks: dict[str, str] = {}
        while time.monotonic() < deadline:
            checks = client.get("/ready").json()["checks"]
            if checks.get("indexes") == "ok":
                break
            time.sleep(0.5)
        assert checks["indexes"] == "ok" and checks["mongo"] == "ok"
        assert "people" in mongo_replica_set[db_name].list_collection_names()
    finally:
        mongo_replica_set.drop_database(db_name)
