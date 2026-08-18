# Security

## Identity & access
- Authentication: OIDC/JWT validated against the org IdP's JWKS
  (`backend/auth/dependencies.py`). The backend is a resource server; it never
  issues or stores passwords.
- Authorization: role claims embedded in the JWT (`require_role(...)`
  dependency). Roles: `clinician`, `reviewer`, `admin`, `service`.
- API Gateway sits in front of the backend Service and terminates authn/rate
  limiting before traffic reaches application pods (Ingress now routes to
  `api-gateway`, not `backend`, directly — update `infra/k8s/base/ingress.yaml`
  accordingly when the gateway is deployed).

## Network
- `default-deny-all` NetworkPolicy, explicit allow rules per Service
  (`backend-allow`). Standard zero-trust-in-cluster posture.
- Egress to third-party APIs (LLM provider, EHR) should additionally be
  restricted at the cloud NAT/firewall layer by destination IP allowlist —
  a NetworkPolicy alone doesn't constrain traffic leaving the cluster's VPC.

## Secrets
- No plaintext secrets in git or CI. `external-secret.yaml` syncs from
  AWS Secrets Manager (swap provider block for GCP Secret Manager / Vault as
  needed) via the External Secrets Operator, refreshed hourly.
- `infra/k8s/base/backend-secret.example.yaml` is retained only as schema
  documentation and is excluded from `kustomization.yaml`.

## Pod-level hardening
Already enforced in `infra/k8s/base/*`: non-root, read-only root filesystem,
dropped capabilities, restricted Pod Security Admission at the namespace
level, no auto-mounted service account token unless a workload needs the k8s
API (`rbac.yaml`).

## Data protection
- TLS in transit everywhere (Ingress terminates external TLS; internal
  service-to-service TLS via service mesh mTLS is the standard next step —
  Linkerd/Istio — not included here to avoid prescribing a mesh choice).
- Encryption at rest for the audit database and any object storage
  (recordings, if retained) is a cloud-provider-level configuration
  (e.g. RDS encryption, S3 SSE-KMS) — enforced by infra provisioning (see
  disaster-recovery layer), not application code.
- PHI never appears in logs or trace attributes (enforced at the otel
  collector — see tracing layer) or in metric labels (enforced by
  instrumentation review — metric labels must be low-cardinality and
  non-identifying by construction).

## Dependencies added
```
python-jose[cryptography]
httpx
```
