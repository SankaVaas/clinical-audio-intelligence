"""
Prometheus instrumentation for the clinical pipeline.

Exposes /metrics on the backend Service. Scraped by the Prometheus Operator
via the ServiceMonitor in infra/monitoring/prometheus/servicemonitor.yaml.
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest

registry = CollectorRegistry()

# --- ASR ---
asr_requests_total = Counter(
    "asr_requests_total", "Transcription requests", ["status"], registry=registry
)
asr_latency_seconds = Histogram(
    "asr_latency_seconds", "Whisper transcription latency",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20), registry=registry
)

# --- LLM / RAG ---
llm_requests_total = Counter(
    "llm_requests_total", "LLM calls", ["model", "status"], registry=registry
)
llm_latency_seconds = Histogram(
    "llm_latency_seconds", "LLM call latency", ["model"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40), registry=registry
)
llm_tokens_total = Counter(
    "llm_tokens_total", "Tokens consumed", ["model", "direction"], registry=registry
)  # direction = prompt|completion — feeds the cost-control layer

# --- Clinical safety ---
risk_flags_total = Counter(
    "risk_flags_total", "Risk engine flags raised", ["severity", "category"], registry=registry
)
human_review_queue_depth = Gauge(
    "human_review_queue_depth", "Items awaiting clinician review", registry=registry
)

# --- Audit ---
audit_write_failures_total = Counter(
    "audit_write_failures_total", "Failed audit log writes (must page on-call)", registry=registry
)

# --- Session / pipeline ---
active_sessions = Gauge("active_sessions", "Concurrent audio sessions", ["tenant_id"], registry=registry)
pipeline_stage_latency_seconds = Histogram(
    "pipeline_stage_latency_seconds", "Per-stage latency", ["stage"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10), registry=registry
)


def metrics_response() -> bytes:
    return generate_latest(registry)
