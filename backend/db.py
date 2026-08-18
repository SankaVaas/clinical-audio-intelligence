"""
Single asyncpg pool, shared by the audit service and the budget store.
One pool, not one-per-module, so connection limits are managed in one place.
"""
import os
import asyncpg

from backend.audit.service import AuditService
from backend.cost.tracker import CostTracker
from backend.cost.store import PostgresBudgetStore

_pool: asyncpg.Pool | None = None
audit_service: AuditService | None = None
cost_tracker: CostTracker | None = None


async def init_db():
    global _pool, audit_service, cost_tracker
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
        # RLS depends on app.current_tenant being set per-connection use;
        # tenancy/middleware.py sets it via set_config on each request's
        # borrowed connection (see backend/tenancy/db.py).
    )
    audit_service = AuditService(_pool)
    cost_tracker = CostTracker(PostgresBudgetStore(_pool))


async def close_db():
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized -- init_db() must run before first use")
    return _pool
