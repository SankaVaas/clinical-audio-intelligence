# Clinical Audio Intelligence — Production Architecture

## Target architecture

```
                Mobile / Web
                     │
                API Gateway
                     │
               Authentication
                     │
            ┌────────▼────────┐
            │ Audio Ingestion │
            └────────┬────────┘
                     │
                Kafka / PubSub
                     │
           ┌─────────▼─────────┐
           │ Speech Processing │
           │  Whisper / ASR    │
           └─────────┬─────────┘
                     │
                Clinical NLP
                     │
           ┌─────────▼─────────┐
           │   LLM / RAG Layer │
           └─────────┬─────────┘
                     │
                Safety Engine
                     │
                Human Review
                     │
                  EHR / API
```

Every hop above is instrumented (metrics + traces), authenticated,
tenant-scoped, and audit-logged. Reliability, security, and compliance are
cross-cutting concerns applied uniformly across the pipeline, not
bolted onto individual stages.

## Repository layout

```
backend/
  main.py                 FastAPI app, CORS from env
  audio/                  capture, session, transcriber (Whisper)
  nlp/                    clinical entity extraction
  soap/                   SOAP note generation
  risk/                   hybrid risk engine
  auth/                   OIDC/JWT validation, RBAC dependency
  audit/                  hash-chained append-only audit log
  tenancy/                tenant context resolution + enforcement
  cost/                   LLM budget tracking and enforcement
  observability/          Prometheus metrics, OpenTelemetry tracing

infra/
  k8s/base/               Deployments, Services, HPA, PDB, Ingress (Kustomize)
  monitoring/              ServiceMonitor, PrometheusRule, Grafana dashboard
  tracing/                 otel-collector deployment + PHI-redacting config
  security/                NetworkPolicy, RBAC, ExternalSecret
  audit/                   Postgres append-only schema
  eval/                    CronJob for nightly model regression
  cost/                    Budget schema, spend-anomaly alerts
  multi-tenancy/           RLS policies, dedicated-namespace isolation option
  dr/                      Velero schedules, RDS Multi-AZ + cross-region replica, runbook

eval/
  harness.py               ASR / NLP / risk-engine evaluation, CI/CD gate
  datasets/                golden-set schema documentation

docs/
  ARCHITECTURE.md          this file
```

## Cross-cutting concerns and where they live

| Concern | Enforced by | Notes |
|---|---|---|
| Scalability / self-healing | `infra/k8s/base` | HPA 3–10 replicas, PDB, topology spread |
| Observability (metrics) | `backend/observability/metrics.py`, `infra/monitoring` | ASR/LLM latency, risk-flag rate, queue depth, audit failures |
| Observability (tracing) | `backend/observability/tracing.py`, `infra/tracing` | Full pipeline trace, PHI stripped at the collector |
| AuthN/AuthZ | `backend/auth`, `infra/security` | OIDC/JWT, role-based, API Gateway fronts the backend |
| Network isolation | `infra/security/network-policy.yaml` | Default-deny, explicit allow per Service |
| Secrets | `infra/security/external-secret.yaml` | No plaintext secrets in git or CI |
| Auditability | `backend/audit`, `infra/audit` | Hash-chained, append-only, DB-enforced |
| Model quality gating | `eval/harness.py`, `infra/eval` | Hard thresholds block promotion; risk sensitivity is non-negotiable |
| Cost governance | `backend/cost`, `infra/cost` | Pre-emptive budget enforcement + anomaly alerting |
| Multi-tenancy | `backend/tenancy`, `infra/multi-tenancy` | Server-resolved tenant ID, Postgres RLS, optional dedicated namespace |
| Disaster recovery | `infra/dr` | RPO 5 min / RTO 30 min, Multi-AZ + cross-region replica, quarterly drills |

## Audio ingestion — resolved
`backend/audio/capture.py` (server-side `sounddevice` mic capture) has been
removed. Audio is now client-captured and streamed to the backend over
`WS /ws/audio` as raw 16-bit PCM binary frames; `backend/audio/ingest.py`
reassembles frames into fixed-duration chunks regardless of client chunking
behavior. Session state moved from a single process-global `AudioSession` to
one instance per connection (`backend/audio/manager.py`), each tagged with
the tenant ID from the caller's validated JWT — this is also what makes
concurrent multi-tenant session state actually correct, not just the
auth/audit/cost layers around it.

**Frontend — done.** `frontend/src/App.tsx` now speaks the real protocol:
mic capture via `AudioWorkletNode` (`src/audio/AudioStreamer.ts`), OIDC login
(`src/auth/AuthProvider.tsx`), `WS /ws/audio` with first-message auth, PCM
streaming, and calls to `/sessions/{id}/analyze`. See `frontend/README.md`
for the full protocol and the runtime-config-injection mechanism that lets
one Docker image serve every environment.

**Known constraint accepted with this design:** sessions are in-process
state, not externalized to Kafka/Redis (deferred per the earlier
Kafka/PubSub decision). A session is pinned to whichever pod accepted its
WebSocket connection and does not survive that pod's restart. Acceptable for
a single continuous conversation; revisit if session resumption across
pods becomes a requirement.

## Not yet implemented (explicitly out of scope of current layers)
- Kafka/PubSub between ingestion and ASR (diagram shows it; current build is
  direct WebSocket-to-ASR — introduce a queue when throughput or ASR-stage
  decoupling requires it, to avoid adding operational surface area
  prematurely).
- Service mesh mTLS for in-cluster traffic (recommended next step once a
  mesh choice — Istio/Linkerd — is made).
- Active-active multi-region serving (current DR posture is active-passive;
  see `infra/dr/runbook.md`).
