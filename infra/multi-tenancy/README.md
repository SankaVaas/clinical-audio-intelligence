# Multi-Tenancy

Two isolation tiers, chosen per tenant based on regulatory/contractual need:

## Tier 1 — Shared compute, RLS-isolated data (default)
- Tenant ID resolved server-side from the JWT, never from client input
  (`backend/tenancy/middleware.py`).
- Postgres Row-Level Security (`infra/multi-tenancy/postgres-rls.sql`) as
  defense in depth: even a missing `WHERE tenant_id = ...` in a query cannot
  leak cross-tenant rows, because the database enforces it independently of
  application code.
- `require_tenant_match()` as a second, explicit guard at the handler level
  against ID-enumeration (IDOR) attacks — returns 404 rather than 403 to
  avoid confirming a resource exists in another tenant.
- Cost budgets (`infra/cost`) and audit logs (`infra/audit`) are already
  tenant-scoped by design — same `tenant_id` column and RLS policy pattern.

## Tier 2 — Dedicated compute (namespace-per-tenant)
For tenants whose contract or regulatory environment requires physical
compute isolation, not just logical: a dedicated namespace
(`infra/multi-tenancy/network-policy-isolation.yaml`) with its own
NetworkPolicy denying all cross-namespace ingress. Same application image,
different deployment target — no code fork.

## What this deliberately does not do
Does not attempt per-tenant database instances by default — that's Tier 2's
job, applied selectively, not the baseline, since it multiplies operational
surface area (migrations, backups, patching) across every tenant.
