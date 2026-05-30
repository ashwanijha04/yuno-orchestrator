"""Cost computation. Decimal throughout — never float — so the cost ledger and
the circuit breaker are exact."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class CostModel:
    """Per-1K-token pricing for one model."""

    input_per_1k: Decimal
    output_per_1k: Decimal

    def cost(
        self,
        tokens_in: int,
        tokens_out: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
    ) -> Decimal:
        # Anthropic prompt caching: cache hit reads at 10% of input price;
        # the first write that populates the cache costs 125%. Zero on providers
        # that don't support caching, so the formula collapses to the simple case.
        # `tokens_in` from the provider is already the *uncached* portion.
        cache_read_cost = self.input_per_1k * Decimal(cache_read_tokens) * Decimal("0.10")
        cache_write_cost = self.input_per_1k * Decimal(cache_creation_tokens) * Decimal("1.25")
        total = (
            self.input_per_1k * Decimal(tokens_in)
            + self.output_per_1k * Decimal(tokens_out)
            + cache_read_cost
            + cache_write_cost
        ) / Decimal(1000)
        return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
