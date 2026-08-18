# Monitoring

Prometheus Operator + Grafana, standard kube-prometheus-stack conventions.

## Components
- `backend/observability/metrics.py` — `prometheus_client` registry exposed at
  `GET /metrics` on the backend. Instrumentation points: ASR latency/count,
  LLM latency/count/tokens (by model), risk-flag counts (by severity/category),
  human-review queue depth, audit write failures, per-stage pipeline latency.
- `prometheus/servicemonitor.yaml` — scrape config, matches the Prometheus
  Operator's default `release: prometheus` selector.
- `prometheus/prometheusrule-alerts.yaml` — SLO-based alerts. `AuditWriteFailure`
  is `page: "true"` — a dropped audit record is a compliance incident, not a
  performance issue.
- `grafana/dashboard-clinical-ai.json` — importable dashboard covering ASR/LLM
  latency, error rate, risk-flag rate, queue depth, token spend, and cluster
  health.

## Prerequisite
`kube-prometheus-stack` (or equivalent Prometheus Operator installation) must
already be running in the cluster; these manifests assume its CRDs
(`ServiceMonitor`, `PrometheusRule`) and label conventions.

## Wiring into the app
```python
# main.py
from observability.metrics import metrics_response
from fastapi import Response

@app.get("/metrics")
def metrics():
    return Response(metrics_response(), media_type="text/plain")
```
Latency/counter calls are added at each pipeline stage (ASR, NLP extraction,
risk scoring, LLM call) — see inline `# TODO(metrics)` markers left in
`audio/transcriber.py`, `nlp/extractor.py`, and `risk/engine.py` for exact
insertion points once those modules are touched by other layers.
