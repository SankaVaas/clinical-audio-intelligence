# Kubernetes Deployment — Clinical Audio Intelligence

## Overview
Backend (FastAPI) and frontend (React/nginx) are packaged as OCI images and
deployed to Kubernetes as independently scalable Deployments behind an
Ingress. Configuration is externalized via ConfigMap/Secret; state (model
cache) is externalized via PVC. No in-cluster component holds unique data —
pods are disposable.

## Layout
```
backend/Dockerfile              multi-stage build, non-root, healthcheck
frontend/Dockerfile             multi-stage build -> nginx-unprivileged
frontend/nginx.conf             SPA routing + /api /ws reverse proxy
infra/k8s/base/
  namespace.yaml                 clinical-ai namespace, restricted PSA
  backend-configmap.yaml         non-secret runtime config
  backend-secret.example.yaml    documents secret schema (not applied by kustomize)
  backend-deployment.yaml        Deployment, PVC, PodDisruptionBudget, HPA
  backend-service.yaml           ClusterIP service
  frontend.yaml                  Deployment + Service
  ingress.yaml                   TLS termination, cert-manager + ingress-nginx
  kustomization.yaml
```

## Application change required for containerization
`backend/main.py` — CORS origins are now read from `ALLOWED_ORIGINS` (env) via
the `backend-config` ConfigMap, replacing the hardcoded `allow_origins=["*"]`.
This is the only application code change; everything else in this layer is
infrastructure.

## Design decisions
| Decision | Rationale |
|---|---|
| `replicas: 3`, `maxUnavailable: 0` on rollout | No capacity loss during deploys of a clinical-facing system |
| `uvicorn --workers 1`, scale via replica count | Whisper model instances are memory-heavy; scale horizontally, not via forked workers per pod |
| PVC-backed model cache (`/app/.cache`) | Avoids re-downloading the ASR model on every pod restart; cuts cold-start readiness from minutes to ~20s |
| `startupProbe` with high `failureThreshold`, tight `livenessProbe` | Tolerates cold-start latency without weakening steady-state liveness sensitivity |
| `readOnlyRootFilesystem: true` + explicit `emptyDir`/PVC mounts | Standard container hardening; only declared paths are writable |
| PodDisruptionBudget + `topologySpreadConstraints` | Maintains availability through node drains and single-AZ failure |
| HPA on CPU + memory, 3–10 replicas | Absorbs ASR/LLM inference load spikes without manual intervention |

## Known limitation — audio ingestion path
`backend/audio/capture.py` currently opens a local audio device via
`sounddevice` on the host running the process. That model is incompatible
with a containerized deployment, where the pod has no relationship to the
end user's microphone. The ingestion layer needs to shift to
client-captured audio streamed to the backend (WebSocket/chunked upload),
per the target architecture. This is tracked as an application-layer change
independent of this deployment layer and is not addressed by these
manifests.

## Deployment
```bash
docker build -t REGISTRY/clinical-ai-backend:v0.1.0  -f backend/Dockerfile .
docker build -t REGISTRY/clinical-ai-frontend:v0.1.0 -f frontend/Dockerfile .
docker push REGISTRY/clinical-ai-backend:v0.1.0
docker push REGISTRY/clinical-ai-frontend:v0.1.0

kubectl create secret generic backend-secrets -n clinical-ai \
  --from-literal=OPENROUTER_API_KEY=sk-... \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k infra/k8s/base
kubectl -n clinical-ai rollout status deployment/backend
kubectl -n clinical-ai rollout status deployment/frontend
```

## Rollback
```bash
kubectl -n clinical-ai rollout undo deployment/backend
kubectl -n clinical-ai rollout undo deployment/frontend
```

## Out of scope for this layer
Metrics collection, distributed tracing, network policy/authn-authz,
durable audit storage, model evaluation gating, LLM cost governance, tenant
isolation, and backup/DR are handled in their respective infrastructure
layers, not here.
