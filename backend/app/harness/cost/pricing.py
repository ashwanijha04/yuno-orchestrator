"""Provider pricing tables (USD per 1K tokens). Approximate public list prices;
update as providers change. Keyed by model name with a conservative default."""

from __future__ import annotations

from decimal import Decimal

from app.harness.cost.models import CostModel

# USD per 1K tokens (input, output).
_PRICING: dict[str, CostModel] = {
    # Anthropic
    "claude-opus-4-7": CostModel(Decimal("0.015"), Decimal("0.075")),
    "claude-sonnet-4-6": CostModel(Decimal("0.003"), Decimal("0.015")),
    "claude-sonnet-4-5": CostModel(Decimal("0.003"), Decimal("0.015")),
    "claude-haiku-4-5": CostModel(Decimal("0.0008"), Decimal("0.004")),
    # OpenAI
    "gpt-4o": CostModel(Decimal("0.0025"), Decimal("0.010")),
    "gpt-4o-mini": CostModel(Decimal("0.00015"), Decimal("0.0006")),
    # Google Gemini
    "gemini-1.5-flash": CostModel(Decimal("0.000075"), Decimal("0.0003")),
    "gemini-2.0-flash": CostModel(Decimal("0.0001"), Decimal("0.0004")),
    "gemini-1.5-pro": CostModel(Decimal("0.00125"), Decimal("0.005")),
    # Deterministic providers
    "stub": CostModel(Decimal("0"), Decimal("0")),
}

# Conservative fallback (errs high) for unknown models, so the cost cap never
# under-charges and trips late.
_DEFAULT = CostModel(Decimal("0.015"), Decimal("0.075"))


def get_cost_model(model_name: str) -> CostModel:
    return _PRICING.get(model_name, _DEFAULT)
