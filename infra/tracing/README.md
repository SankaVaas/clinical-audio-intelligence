# Distributed Tracing

OpenTelemetry, OTLP transport, collector fans out to Tempo (traces) and
Prometheus (span metrics). Standard vendor-neutral setup — swapping Tempo for
Jaeger or a SaaS backend (Honeycomb, Datadog) is a one-line exporter change,
not an application change.

## Trace boundary
API Gateway → Backend (FastAPI auto-instrumented) → ASR stage → NLP extraction
→ LLM/RAG call (httpx auto-instrumented) → Risk Engine → Audit write → EHR call.
Each manual pipeline stage uses the `@traced_stage("...")` decorator from
`backend/observability/tracing.py`.

## PHI boundary — critical
The collector's `attributes/redact_phi` processor strips transcript text and
patient identifiers from span attributes before export. Spans carry *timing
and outcome*, never clinical content. Enforce this at the collector, not just
in application code, so a future instrumentation mistake in the app can't leak
PHI into a tracing backend outside the compliance boundary.
