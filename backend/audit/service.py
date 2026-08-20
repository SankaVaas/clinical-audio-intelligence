"""
Audit service: writes hash-chained entries to Postgres, synchronously and
durably. This replaces risk/engine.py's in-memory get_audit_log().

Design constraints:
- Write failures increment audit_write_failures_total (pages on-call — see
  monitoring layer) and raise, rather than silently continuing. A clinical
  action that can't be audited should not be treated as if it succeeded
  silently -- callers decide whether to fail the request or degrade
  explicitly, but the failure is never swallowed.
- No UPDATE/DELETE ever issued against the audit table; enforced at both the
  application layer (this module never constructs those statements) and the
  database layer (REVOKE UPDATE/DELETE in the schema).
"""
import asyncpg
from backend.audit.models import AuditEntry
from backend.observability.metrics import audit_write_failures_total
from backend.tenancy.db import acquire_tenant_conn


class AuditService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def record(self, entry: AuditEntry) -> AuditEntry:
        try:
            async with acquire_tenant_conn(self.pool, entry.tenant_id) as conn:
                async with conn.transaction():
                    # Serializes concurrent writers for this tenant so the hash chain can't fork under concurrency
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", entry.tenant_id)

                    row = await conn.fetchrow(
                        "SELECT entry_hash FROM audit_log WHERE tenant_id = $1 "
                        "ORDER BY id DESC LIMIT 1", entry.tenant_id,
                    )
                    entry.prev_hash = row["entry_hash"] if row else ""
                    entry.entry_hash = entry.compute_hash()

                    await conn.execute(
                        """
                        INSERT INTO audit_log
                            (tenant_id, actor_id, action, resource_type, resource_id,
                             metadata, timestamp, prev_hash, entry_hash)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        """,
                        entry.tenant_id, entry.actor_id, entry.action,
                        entry.resource_type, entry.resource_id,
                        entry.metadata, entry.timestamp, entry.prev_hash, entry.entry_hash,
                    )
        except Exception:
            audit_write_failures_total.inc()
            raise
        return entry

    async def verify_chain(self, tenant_id: str) -> bool:
        """Integrity check: recompute hashes across the full chain for a
        tenant. Run on a schedule (see infra/audit) and before any
        compliance export."""
        async with acquire_tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(
                "SELECT * FROM audit_log WHERE tenant_id = $1 ORDER BY id ASC", tenant_id
            )
        prev = ""
        for row in rows:
            entry = AuditEntry(
                tenant_id=row["tenant_id"], actor_id=row["actor_id"], action=row["action"],
                resource_type=row["resource_type"], resource_id=row["resource_id"],
                metadata=row["metadata"], timestamp=row["timestamp"].isoformat(),
                prev_hash=row["prev_hash"],
            )
            if entry.prev_hash != prev:
                return False
            expected_hash = entry.compute_hash()
            if expected_hash != row["entry_hash"]:
                return False
            prev = row["entry_hash"]
        return True
