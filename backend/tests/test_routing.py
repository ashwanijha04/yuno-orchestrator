"""Model routing: task_type -> provider chain, key-filtered fallback, stub safety net."""

from __future__ import annotations

import pytest

from app.config import settings
from app.harness import routing


@pytest.fixture
def keys(monkeypatch):
    """Helper to set which provider keys are 'present'."""
    def _set(anthropic=None, openai=None, gemini=None):
        monkeypatch.setattr(settings, "anthropic_api_key", anthropic)
        monkeypatch.setattr(settings, "openai_api_key", openai)
        monkeypatch.setattr(settings, "gemini_api_key", gemini)
        monkeypatch.setattr(settings, "llm_mode", "live")
    return _set


def _names(candidates):
    return [c.provider.name for c in candidates]


def test_coding_routes_to_anthropic_first(keys):
    keys(anthropic="a", openai="o", gemini="g")
    c = routing.resolve(task_type="coding", explicit_provider=None, explicit_model=None)
    assert _names(c)[0] == "anthropic" and "openai" in _names(c)


def test_conversation_routes_to_gemini_first(keys):
    keys(anthropic="a", openai="o", gemini="g")
    c = routing.resolve(task_type="conversation", explicit_provider=None, explicit_model=None)
    assert _names(c)[0] == "gemini"


def test_fallback_skips_providers_without_keys(keys):
    # conversation prefers gemini, but only openai has a key -> gemini skipped.
    keys(anthropic=None, openai="o", gemini=None)
    c = routing.resolve(task_type="conversation", explicit_provider=None, explicit_model=None)
    assert _names(c) == ["openai"]


def test_auto_honors_explicit_then_falls_back(keys):
    keys(anthropic="a", openai="o", gemini=None)
    c = routing.resolve(task_type="auto", explicit_provider="anthropic", explicit_model="claude-sonnet-4-6")
    assert _names(c)[0] == "anthropic"
    assert c[0].model_name == "claude-sonnet-4-6"
    assert "openai" in _names(c)  # fallback chain appended


def test_no_keys_falls_back_to_stub(keys):
    keys(anthropic=None, openai=None, gemini=None)
    c = routing.resolve(task_type="coding", explicit_provider=None, explicit_model=None)
    assert _names(c) == ["stub"]


def test_stub_mode_never_routes():
    c = routing.resolve(task_type="coding", explicit_provider="anthropic", explicit_model="x", mode="stub")
    assert _names(c) == ["stub"]
