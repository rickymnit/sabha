"""Tracing is off unless configured; when on, spans carry the service identity and reach the exporter."""

from __future__ import annotations

from typing import Any

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from sabha_core.settings import Settings
from sabha_core.telemetry import setup_tracing

BASE: dict[str, Any] = {
    "app_env": "test",
    "mongo_uri": "mongodb://localhost:27017/?replicaSet=rs0",
    "redis_url": "redis://localhost:6380/0",
    "s3_bucket_audio": "a",
    "s3_bucket_artefacts": "b",
    "s3_bucket_backups": "c",
    "oidc_issuer": "https://auth.example.com",
    "oidc_audience": "api",
    "oidc_client_id": "web",
}


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[call-arg]  # settings option


def test_tracing_is_off_without_an_endpoint() -> None:
    assert setup_tracing("sabha-api", settings()) is None


def test_spans_reach_the_exporter_with_service_identity() -> None:
    exporter = InMemorySpanExporter()
    provider = setup_tracing("sabha-api", settings(git_sha="abc1234"), exporter=exporter)
    assert provider is not None
    with provider.get_tracer("test").start_as_current_span("work"):
        pass
    provider.shutdown()
    [span] = exporter.get_finished_spans()
    assert span.name == "work"
    assert span.resource.attributes["service.name"] == "sabha-api"
    assert span.resource.attributes["deployment.environment.name"] == "test"
    assert span.resource.attributes["vcs.ref.head.revision"] == "abc1234"


def test_an_endpoint_turns_tracing_on() -> None:
    provider = setup_tracing("sabha-api", settings(otel_exporter_otlp_endpoint="http://localhost:4318"))
    assert provider is not None
    provider.shutdown()
