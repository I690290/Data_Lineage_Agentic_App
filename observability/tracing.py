"""OpenTelemetry tracing setup — local Jaeger exporter."""
from __future__ import annotations

import functools
from typing import Any, Callable

_tracer = None


def setup_tracing(
    service_name: str = "data-lineage-agent",
    otlp_endpoint: str = "http://localhost:4317",
) -> Any:
    """Initialise OTel TracerProvider with Jaeger OTLP exporter.

    Args:
        service_name: Service name attribute for all spans.
        otlp_endpoint: OTLP gRPC endpoint (Jaeger all-in-one default port 4317).

    Returns:
        A configured opentelemetry ``Tracer`` instance.
    """
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("lineage-agent")
        print(f"[tracing] OTel tracing enabled → {otlp_endpoint}")
        return _tracer
    except ImportError:
        print("[tracing] opentelemetry-sdk not installed — tracing disabled")
        return _NoopTracer()
    except Exception as exc:
        print(f"[tracing] Tracing setup failed (non-fatal): {exc}")
        return _NoopTracer()


def get_tracer() -> Any:
    """Return the global tracer, initialising with defaults if not yet set.

    Returns:
        Configured tracer or no-op tracer.
    """
    global _tracer
    if _tracer is None:
        from src.config import settings
        _tracer = setup_tracing(
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        )
    return _tracer


def trace_node(node_name: str) -> Callable:
    """Decorator to wrap a LangGraph node function with an OTel span.

    Args:
        node_name: Name used for the span and ``lineage.node.name`` attribute.

    Returns:
        Decorator function.

    Example::

        @trace_node("cobol_agent")
        def cobol_extraction_agent(state):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            tracer = get_tracer()
            try:
                from opentelemetry import trace as otel_trace
                with tracer.start_as_current_span(node_name) as span:
                    span.set_attribute("lineage.node.name", node_name)
                    span.set_attribute("lineage.file_path", state.get("file_path", ""))
                    span.set_attribute("lineage.language", state.get("language", ""))
                    result = fn(state)
                    span.set_attribute("lineage.assertions_count", len(result.get("extracted_assertions", [])))
                    return result
            except ImportError:
                return fn(state)
        return wrapper
    return decorator


def record_llm_span(
    tracer: Any,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    action_type: str = "ASSERT",
    confidence: float = 0.0,
) -> None:
    """Record a child span for a single Bedrock LLM invocation.

    Args:
        tracer: OTel tracer instance.
        model_id: Bedrock model ID string.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens produced.
        action_type: ReAct action type: ``"THINK"``, ``"ACT"``, ``"OBSERVE"``, ``"ASSERT"``.
        confidence: Assertion confidence score.
    """
    try:
        with tracer.start_as_current_span("bedrock_invoke") as span:
            span.set_attribute("gen_ai.system", "aws.bedrock")
            span.set_attribute("gen_ai.request.model", model_id)
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            span.set_attribute("lineage.agent.action_type", action_type)
            span.set_attribute("lineage.assertion.confidence", confidence)
    except Exception:
        pass


class _NoopTracer:
    """No-op tracer for when OTel is not available."""

    def start_as_current_span(self, name: str) -> Any:
        """Return a no-op context manager."""
        return _NoopSpan()

    def start_span(self, name: str) -> Any:
        """Return a no-op span."""
        return _NoopSpan()


class _NoopSpan:
    """No-op span context manager."""

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        """Silently ignore attribute setting."""
