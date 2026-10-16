"""OpenTelemetry tracing set-up shared by the API and the workers.

Tracing is on only when OTEL_EXPORTER_OTLP_ENDPOINT is set: spans are batched and sent over OTLP/HTTP to
`<endpoint>/v1/traces`. Without it nothing is exported and no background thread starts. The collector must keep data
in India (golden rule 12).

The API connects FastAPI to the returned provider (sabha_api.main); the workers will do the same for Celery (P2.4).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from sabha_core.settings import Settings


def package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def setup_tracing(
    service_name: str, settings: Settings, *, exporter: SpanExporter | None = None
) -> TracerProvider | None:
    """A tracer provider exporting to the configured collector, or None when tracing is off.

    `exporter` replaces the OTLP exporter (tests use an in-memory one). The caller shuts the provider down on exit,
    which flushes spans still in the batch.
    """
    if exporter is None:
        if settings.otel_exporter_otlp_endpoint is None:
            return None
        exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": package_version(service_name),
            "deployment.environment.name": settings.app_env,
            **({"vcs.ref.head.revision": settings.git_sha} if settings.git_sha else {}),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider
