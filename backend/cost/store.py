"""
Postgres-backed implementation of the budget store CostTracker depends on.
Schema: infra/cost/postgres-budget-schema.sql
"""
import asyncpg
from backend.cost.tracker import Budget


class PostgresBudgetStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get(self, tenant_id: str) -> Budget:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT monthly_limit_usd, spent_usd FROM tenant_budgets WHERE tenant_id = $1",
                tenant_id,
            )
        if row is None:
            # Unknown tenant: default to a conservative fail-closed budget
            # rather than unlimited spend. Provisioning a real budget row is
            # part of tenant onboarding (infra/multi-tenancy).
            return Budget(tenant_id=tenant_id, monthly_limit_usd=0.0, spent_usd=0.0)
        return Budget(tenant_id=tenant_id, monthly_limit_usd=float(row["monthly_limit_usd"]),
                      spent_usd=float(row["spent_usd"]))

    async def increment_spend(self, tenant_id: str, cost_usd: float):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tenant_budgets SET spent_usd = spent_usd + $1 WHERE tenant_id = $2",
                cost_usd, tenant_id,
            )
