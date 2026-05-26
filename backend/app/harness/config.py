"""Harness configuration resolution + object construction.

Resolution hierarchy (lowest to highest precedence):
    env defaults  <  per-agent `agents.harness`  <  per-node `harness_overrides`

Config is declarative (lists of {type, ...} dicts); the factories below turn it
into validator/interceptor instances. Providers are selected by LLM_MODE.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
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


def get_provider(mode: str | None = None):
    """Select a provider by harness mode. Stub/replay are wired by the caller
    with their script/recording; this returns the live providers."""
    mode = mode or settings.llm_mode
    if settings.llm_provider_default == "anthropic":
        from app.harness.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    raise ValueError(f"unsupported provider default: {settings.llm_provider_default}")
