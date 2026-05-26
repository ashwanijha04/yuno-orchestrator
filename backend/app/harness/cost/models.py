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

    def cost(self, tokens_in: int, tokens_out: int) -> Decimal:
        total = (
            self.input_per_1k * Decimal(tokens_in)
            + self.output_per_1k * Decimal(tokens_out)
        ) / Decimal(1000)
        return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
