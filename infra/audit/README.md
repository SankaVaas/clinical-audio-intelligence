# Auditability

Replaces the in-memory `risk/engine.py` audit list with a durable,
tamper-evident, append-only log — a compliance requirement for a clinical
system (HIPAA §164.312(b) and equivalent).

## Components
- `backend/audit/models.py` — `AuditEntry` with SHA-256 hash chaining.
- `backend/audit/service.py` — `AuditService`: writes are synchronous,
  failures are never swallowed (`audit_write_failures_total` pages on-call),
  and `verify_chain()` performs integrity verification.
- `infra/audit/postgres-audit-schema.sql` — append-only table enforced at
  three layers: application (no UPDATE/DELETE statements exist in code),
  grants (`REVOKE UPDATE, DELETE`), and a trigger as a final backstop.

## What gets audited
Every clinically or compliance-relevant action: session start/finalize, risk
flags raised, SOAP note generation/edit/export, human review decisions,
EHR writes, auth events (login, role changes), and PHI access/export. Not
audited: metrics/health checks, static asset requests.

## Retention & export
Retention period follows applicable regulatory requirement (commonly 6+
years under HIPAA for covered entities — confirm with the org's compliance
officer, not assumed here). Export path: `verify_chain()` must pass before
any compliance/legal export is produced.

## Scheduled integrity check
Run `AuditService.verify_chain()` per tenant on a daily CronJob (see
`infra/eval` pattern — same CronJob shape, different job) and alert
(`page: "true"`) on any chain break.
