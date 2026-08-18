"""
Acquires a pooled connection and sets the RLS session variable
(app.current_tenant) that infra/multi-tenancy/postgres-rls.sql's policies
check. Use this instead of pool.acquire() directly for any query touching
a tenant-scoped table (audio_sessions, clinical_notes, audit_log).
"""
from contextlib import asynccontextmanager
import asyncpg


@asynccontextmanager
async def acquire_tenant_conn(pool: asyncpg.Pool, tenant_id: str):
    async with pool.acquire() as conn:
        # set_config(..., is_local=false) scopes to this connection for its
        # lifetime in the pool checkout -- reset happens implicitly when the
        # connection is released back to the pool and reused, since the next
        # checkout sets it again before any tenant-scoped query runs.
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
        yield conn
