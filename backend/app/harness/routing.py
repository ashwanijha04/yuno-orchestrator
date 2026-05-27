"""ModelRouter — picks provider+model by task type, with a key-filtered fallback
chain.

    coding       -> Anthropic (Sonnet)   then OpenAI
    normal       -> OpenAI (4o-mini)      then Anthropic
    conversation -> Gemini (Flash)        then OpenAI, then Anthropic
    auto         -> the agent's explicit provider/model, then the 'normal' chain

Candidates whose provider has no API key configured are skipped, so the chain
degrades to whatever is available; if nothing is, it falls back to the deterministic
stub so the system always responds.
"""

from __future__ import annotations

from app.config import settings
from app.harness.call import ProviderCandidate
from app.harness.cost import get_cost_model

ROUTES: dict[str, list[tuple[str, str]]] = {
    "coding": [("anthropic", "claude-sonnet-4-6"), ("openai", "gpt-4o")],
    "normal": [("openai", "gpt-4o-mini"), ("anthropic", "claude-haiku-4-5")],
    "conversation": [("gemini", "gemini-1.5-flash"), ("openai", "gpt-4o-mini"), ("anthropic", "claude-haiku-4-5")],
}
DEFAULT_TASK = "normal"


def _has_key(provider: str) -> bool:
    return {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "gemini": bool(settings.gemini_api_key),
    }.get(provider, False)


def _provider_for(name: str):
    if name == "anthropic":
        from app.harness.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        from app.harness.providers.openai import OpenAIProvider

        return OpenAIProvider()
    if name == "gemini":
        from app.harness.providers.gemini import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"unknown provider {name!r}")


def _stub_candidate(model_name: str = "stub") -> ProviderCandidate:
    from app.harness.providers import Script, StubProvider

    return ProviderCandidate(StubProvider(Script([]), strict=False), model_name, get_cost_model(model_name))


def resolve(
    *,
    task_type: str | None,
    explicit_provider: str | None,
    explicit_model: str | None,
    mode: str | None = None,
) -> list[ProviderCandidate]:
    """Ordered provider candidates (primary first, then fallbacks)."""
    mode = mode or settings.llm_mode
    if mode in ("stub", "replay"):
        return [_stub_candidate(explicit_model or "stub")]

    tt = (task_type or "auto").lower()
    pairs: list[tuple[str, str]] = []
    if tt in ROUTES:
        pairs = list(ROUTES[tt])
    else:  # 'auto' — honor the agent's explicit choice, then fall back
        if explicit_provider and explicit_model:
            pairs.append((explicit_provider, explicit_model))
        for pm in ROUTES[DEFAULT_TASK]:
            if pm not in pairs:
                pairs.append(pm)

    available = [(p, m) for (p, m) in pairs if _has_key(p)]
    if not available:
        # No keys for any routed provider — stay up via the stub.
        return [_stub_candidate(explicit_model or (pairs[0][1] if pairs else "stub"))]

    return [ProviderCandidate(_provider_for(p), m, get_cost_model(m)) for (p, m) in available]
