"""The demo circuit breaker. Before each call, estimate its cost and block if it
would push the run over its budget. After each call, add actual cost to the
running total."""

from __future__ import annotations

from app.harness.call import HarnessedCall
from app.harness.interceptors.base import InterceptorDecision


class CostCapInterceptor:
    name = "cost_cap"

    async def before(self, call: HarnessedCall) -> InterceptorDecision:
        if call.budget.cap_usd is None:
            return InterceptorDecision(action="continue")
        est_tokens = call.provider.estimate_tokens(call.request)
        # Treat the estimate as output tokens (the expensive side) to err high.
        estimated_cost = call.cost_model.cost(0, est_tokens)
        if call.budget.would_exceed(estimated_cost):
            return InterceptorDecision(
                action="block",
                reason=(
                    f"cost cap ${call.budget.cap_usd} would be exceeded "
                    f"(spent ${call.budget.spent_usd}, est +${estimated_cost})"
                ),
            )
        return InterceptorDecision(action="continue")

    async def after(self, call: HarnessedCall) -> None:
        call.budget.add(call.cost_usd)
