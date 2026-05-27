"""Harness configuration resolution + object construction.

Resolution hierarchy (lowest to highest precedence):
    env defaults  <  per-agent `agents.harness`  <  per-node `harness_overrides`

Config is declarative (lists of {type, ...} dicts); the factories below turn it
into validator/interceptor instances. Providers are selected by LLM_MODE.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.harness.call import BudgetTracker, HarnessedCall, LLMRequest
from app.harness.cost import get_cost_model
from app.harness.interceptors import CostCapInterceptor, TraceInterceptor
from app.harness.validators import JSONSchemaValidator, MaxLengthValidator

VALIDATOR_REGISTRY = {
    "json_schema": lambda c: JSONSchemaValidator(schema=c.get("schema")),
    "max_length": lambda c: MaxLengthValidator(max_chars=c.get("max_chars", 10_000)),
}

INTERCEPTOR_REGISTRY = {
    "cost_cap": lambda c: CostCapInterceptor(),
    "trace": lambda c: TraceInterceptor(),
}

_ENV_DEFAULTS: dict[str, Any] = {
    "max_attempts": 3,
    "retry_on": ["rate_limit", "timeout", "validation_failure"],
    "validators": [{"type": "max_length"}],
    "interceptors": [{"type": "trace"}, {"type": "cost_cap"}],
}


def resolve_harness_config(
    agent_harness: dict | None = None, node_overrides: dict | None = None
) -> dict:
    merged = dict(_ENV_DEFAULTS)
    for layer in (agent_harness or {}, node_overrides or {}):
        for key, value in layer.items():
            merged[key] = value
    return merged


def build_validators(config: dict) -> list:
    out = []
    for spec in config.get("validators", []):
        factory = VALIDATOR_REGISTRY.get(spec["type"])
        if factory:
            out.append(factory(spec))
    return out


def build_interceptors(config: dict) -> list:
    out = []
    for spec in config.get("interceptors", []):
        factory = INTERCEPTOR_REGISTRY.get(spec["type"])
        if factory:
            out.append(factory(spec))
    return out


@dataclass
class HarnessRuntime:
    """Resolved, ready-to-use harness behaviour for one agent: max retries plus
    constructed validator/interceptor instances."""

    max_attempts: int = 3
    validators: list = field(default_factory=list)
    interceptors: list = field(default_factory=list)


def resolve_runtime(agent_harness: dict | None = None, node_overrides: dict | None = None) -> HarnessRuntime:
    config = resolve_harness_config(agent_harness, node_overrides)
    return HarnessRuntime(
        max_attempts=int(config.get("max_attempts", 3)),
        validators=build_validators(config),
        interceptors=build_interceptors(config),
    )


def build_harnessed_call(
    *,
    request: LLMRequest,
    provider: Any,
    runtime: HarnessRuntime,
    budget: BudgetTracker,
    run_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
) -> HarnessedCall:
    """Single construction point for a HarnessedCall (factory). Centralizing it
    keeps call assembly consistent as tool-aware calls arrive in Phase 5."""
    return HarnessedCall(
        request=request,
        provider=provider,
        cost_model=get_cost_model(request.model_name),
        validators=runtime.validators,
        interceptors=runtime.interceptors,
        budget=budget,
        max_attempts=runtime.max_attempts,
        run_id=run_id,
        agent_id=agent_id,
    )


def get_provider(mode: str | None = None):
    """Select a provider by harness mode.

    - stub:   deterministic, no API key needed (canned response when unscripted)
    - live/record: the configured live provider (Anthropic by default)
    Replay is wired by the caller with a recording (Phase 9).
    """
    mode = mode or settings.llm_mode
    if mode == "stub":
        from app.harness.providers import Script, StubProvider

        return StubProvider(Script([]), strict=False)
    if settings.llm_provider_default == "anthropic":
        from app.harness.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if settings.llm_provider_default == "openai":
        from app.harness.providers.openai import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"unsupported provider default: {settings.llm_provider_default}")
