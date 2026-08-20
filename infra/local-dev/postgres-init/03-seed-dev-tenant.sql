-- Without this row, backend/cost/store.py's PostgresBudgetStore.get()
-- returns a $0 budget for any unknown tenant (fail-closed by design --
-- see infra/cost/README.md), which would make every /analyze call 429
-- immediately. This seeds a generous local-dev budget for the tenant ID
-- the frontend's DEV_AUTH_BYPASS uses by default (see
-- frontend/public/env.js's DEV_TENANT_ID).
INSERT INTO tenant_budgets (tenant_id, monthly_limit_usd, spent_usd)
VALUES ('dev-tenant', 50.00, 0.00)
ON CONFLICT (tenant_id) DO NOTHING;
