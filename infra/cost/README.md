# Cost Controls

Per-tenant LLM spend tracking with pre-emptive budget enforcement, not just
after-the-fact alerting.

## Components
- `backend/cost/tracker.py` — `CostTracker.call_llm()` wraps every LLM call:
  checks budget before calling, records real token usage after, raises
  `BudgetExceeded` (mapped to HTTP 429) rather than allowing the call through.
- `infra/cost/postgres-budget-schema.sql` — per-tenant budget/spend table,
  monthly reset function (invoke via CronJob on the 1st of each month).
- `infra/cost/prometheusrule-budget-alerts.yaml` — anomaly detection
  (token-rate spike vs. yesterday) and budget-proximity warnings, independent
  of the hard enforcement in the tracker.

## Design choice: enforcement in two places
The tracker blocks at the API boundary (fast, per-request). The Prometheus
rule catches slower-moving anomalies (e.g. a legitimate but abnormal usage
pattern that hasn't yet tripped a hard budget limit). Neither replaces the
other.

## Pricing table maintenance
`PRICING` in `tracker.py` is a static table mirroring the provider's pricing
page — it is not fetched live. Add a recurring calendar reminder (not a
code mechanism) to review it against actual provider invoices monthly.
