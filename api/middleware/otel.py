from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from config.settings import settings
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

_INSTRUMENTED = False
_TRACER_PROVIDER = None


def instrument_app(app: Any) -> None:
    """Apply OTel instrumentation to FastAPI app."""
    global _INSTRUMENTED
    if _INSTRUMENTED:
        return
    try:
        tracer_provider = _get_tracer_provider()
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=tracer_provider,
            server_request_hook=_server_request_hook,
            client_response_hook=_client_response_hook,
        )
        _INSTRUMENTED = True
        print(f"[otel] FastAPI instrumentation enabled -> {settings.otel_exporter_otlp_endpoint}")
    except Exception as exc:  # noqa: BLE001
        print(f"[otel] Failed to instrument FastAPI app (non-fatal): {exc}")


def _get_tracer_provider() -> Any:
    """Create or return a singleton OTEL tracer provider."""
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=str(settings.otel_exporter_otlp_endpoint).startswith("http://"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider
    return provider


def _server_request_hook(span: Any, scope: dict[str, Any]) -> None:
    """Attach lineage-specific request metadata to server spans."""
    if span is None or not getattr(span, "is_recording", lambda: False)():
        return
    query_params = parse_qs((scope.get("query_string") or b"").decode("utf-8"))
    route = scope.get("path", "")
    method = scope.get("method", "")
    span.set_attribute("lineage.component", "fastapi")
    span.set_attribute("lineage.route", route)
    span.set_attribute("lineage.http_method", method)
    span.set_attribute("lineage.domain", _route_domain(route))
    for key in ("repo_path", "file_path", "language", "run_id"):
        value = query_params.get(key, [""])[0]
        if value:
            span.set_attribute(f"lineage.{key}", value)

def _client_response_hook(span: Any, scope: dict[str, Any], message: dict[str, Any]) -> None:
    """Attach response metadata to server spans."""
    if span is None or not getattr(span, "is_recording", lambda: False)():
        return
    if message.get("type") != "http.response.start":
        return
    span.set_attribute("lineage.http_status_code", int(message.get("status", 0) or 0))
    span.set_attribute(
        "lineage.response.headers_count",
        len(message.get("headers", []) or []),
    )


def _route_domain(route: str) -> str:
    """Classify API routes into lineage-specific domains."""
    if route.startswith("/api/eval"):
        return "evaluation"
    if route.startswith("/api/rag"):
        return "retrieval"
    if route.startswith("/api/lineage"):
        return "lineage"
    return "api"
