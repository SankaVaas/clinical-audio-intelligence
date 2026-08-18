"""
OpenTelemetry setup. Traces the full request path:
API Gateway -> Backend -> ASR -> NLP -> LLM/RAG -> Risk Engine -> Audit -> EHR.

Exported via OTLP to the in-cluster otel-collector, which fans out to
Tempo/Jaeger (traces) and can also derive span metrics.
"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


def configure_tracing(app, service_name: str = "clinical-ai-backend"):
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("APP_VERSION", "unknown"),
        "deployment.environment": os.getenv("ENVIRONMENT", "production"),
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector.clinical-ai.svc.cluster.local:4317"),
        insecure=True,  # mTLS terminated by the mesh/sidecar, not the app -- see security layer
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)   # auto: HTTP + WS request spans
    HTTPXClientInstrumentor().instrument()     # auto: outbound calls to OpenRouter/EHR

    return trace.get_tracer(service_name)


tracer = trace.get_tracer("clinical-ai-backend")


def traced_stage(stage_name: str):
    """Decorator for manual spans around pipeline stages not covered by
    auto-instrumentation (Whisper inference, risk scoring, SOAP generation)."""
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"pipeline.{stage_name}") as span:
                span.set_attribute("pipeline.stage", stage_name)
                try:
                    result = await fn(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
        return wrapper
    return decorator
