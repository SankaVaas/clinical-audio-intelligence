CREATE TABLE tenant_budgets (
    tenant_id         TEXT PRIMARY KEY,
    monthly_limit_usd NUMERIC(10,2) NOT NULL,
    spent_usd         NUMERIC(10,2) NOT NULL DEFAULT 0,
    period_start      DATE NOT NULL DEFAULT date_trunc('month', now())
);

-- Reset spend at the start of each billing period; run via CronJob.
CREATE OR REPLACE FUNCTION reset_monthly_budgets() RETURNS void AS $$
BEGIN
    UPDATE tenant_budgets
    SET spent_usd = 0, period_start = date_trunc('month', now())
    WHERE period_start < date_trunc('month', now());
END;
$$ LANGUAGE plpgsql;
