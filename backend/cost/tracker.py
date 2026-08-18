"""
LLM cost tracking and budget enforcement.

Wraps every LLM call so token usage is recorded (feeds
llm_tokens_total in observability/metrics.py) and checked against a
per-tenant budget before the call is made -- cost control has to be
pre-emptive (block the call), not just observational (alert after the
fact), or a runaway loop can burn the monthly budget in minutes.
"""
import os
from dataclasses import dataclass

from backend.observability.metrics import llm_requests_total, llm_latency_seconds, llm_tokens_total

# USD per 1K tokens -- keep in sync with the provider's actual pricing page;
# this is a static table, not fetched live, so it needs a periodic review.
PRICING = {
    "mistral-7b": {"prompt": 0.00007, "completion": 0.00007},
}


@dataclass
class Budget:
    tenant_id: str
    monthly_limit_usd: float
    spent_usd: float


class BudgetExceeded(Exception):
    pass


class CostTracker:
    def __init__(self, budget_store):
        self.budget_store = budget_store   # backing store: Postgres/Redis, see infra/cost

    async def check_budget(self, tenant_id: str, estimated_cost_usd: float):
        budget = await self.budget_store.get(tenant_id)
        if budget.spent_usd + estimated_cost_usd > budget.monthly_limit_usd:
            raise BudgetExceeded(
                f"tenant {tenant_id} would exceed monthly budget "
                f"(${budget.spent_usd:.2f} + ${estimated_cost_usd:.2f} > ${budget.monthly_limit_usd:.2f})"
            )

    async def record_usage(self, tenant_id: str, model: str, prompt_tokens: int, completion_tokens: int):
        price = PRICING.get(model, {"prompt": 0, "completion": 0})
        cost = prompt_tokens / 1000 * price["prompt"] + completion_tokens / 1000 * price["completion"]
        await self.budget_store.increment_spend(tenant_id, cost)

        llm_tokens_total.labels(model=model, direction="prompt").inc(prompt_tokens)
        llm_tokens_total.labels(model=model, direction="completion").inc(completion_tokens)
        return cost

    async def call_llm(self, tenant_id: str, model: str, fn, *args, **kwargs):
        """Wraps an LLM call: pre-flight budget check, metrics, post-call
        cost recording. `fn` is the actual OpenRouter call."""
        # Conservative pre-flight estimate; corrected with real token counts after the call.
        await self.check_budget(tenant_id, estimated_cost_usd=0.01)

        with llm_latency_seconds.labels(model=model).time():
            try:
                response = await fn(*args, **kwargs)
                llm_requests_total.labels(model=model, status="success").inc()
            except Exception:
                llm_requests_total.labels(model=model, status="error").inc()
                raise

        usage = response.get("usage", {})
        await self.record_usage(
            tenant_id, model,
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
        )
        return response
