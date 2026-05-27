"""Deterministic provider for tests and demo fixtures.

Backed by a Script: an ordered list of {match, response} entries. Resolution is
first-unused-match-wins, matched by agent_id / call_index / content_contains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.harness.call import LLMRequest, LLMResponse, ToolCall
from app.harness.providers.base import FatalError, RetryableError


@dataclass
class ScriptEntry:
    match: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    raises: str | None = None  # 'retryable' | 'fatal'


class Script:
    """An ordered list of scripted responses. Build from a list of dicts
    (e.g. parsed YAML) or programmatically."""

    def __init__(self, entries: list[dict] | None = None):
        self.entries: list[ScriptEntry] = [
            ScriptEntry(
                match=e.get("match", {}),
                response=e.get("response", {}),
                raises=e.get("raises"),
            )
            for e in (entries or [])
        ]
        self._used: set[int] = set()

    def reset(self) -> None:
        self._used.clear()

    def resolve(self, request: LLMRequest, call_index: int) -> ScriptEntry | None:
        agent_id = str(request.metadata.get("agent_id", ""))
        text = _request_text(request)
        for i, entry in enumerate(self.entries):
            if i in self._used:
                continue
            m = entry.match
            if "agent_id" in m and str(m["agent_id"]) != agent_id:
                continue
            if "call_index" in m and int(m["call_index"]) != call_index:
                continue
            if "content_contains" in m and m["content_contains"] not in text:
                continue
            self._used.add(i)
            return entry
        return None


def _request_text(request: LLMRequest) -> str:
    parts: list[str] = []
    for msg in request.messages:
        if isinstance(msg.content, str):
            parts.append(msg.content)
        else:
            parts.extend(getattr(b, "text", "") for b in msg.content)
    return "\n".join(parts)


class StubProvider:
    name = "stub"
    supports_images = True

    def __init__(self, script: Script, strict: bool = True):
        self.script = script
        self.strict = strict
        self._call_index = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        idx = self._call_index
        self._call_index += 1
        entry = self.script.resolve(request, idx)

        if entry is None:
            if self.strict:
                raise FatalError(
                    f"No script entry for agent={request.metadata.get('agent_id')} "
                    f"call_index={idx}"
                )
            # Unscripted (lenient) mode: a visible canned response so runs are
            # demoable without keys. Set LLM_MODE=live for real output.
            text = _request_text(request)
            return LLMResponse(
                content=f"[stub] acknowledged: {text[:160]}",
                tokens_in=max(1, len(text) // 4),
                tokens_out=12,
                finish_reason="end_turn",
            )

        if entry.raises == "retryable":
            raise RetryableError("scripted retryable error")
        if entry.raises == "fatal":
            raise FatalError("scripted fatal error")

        r = entry.response
        tool_calls = [
            ToolCall(id=tc.get("id", f"tc_{i}"), name=tc["name"], input=tc.get("input", {}))
            for i, tc in enumerate(r.get("tool_calls", []))
        ]
        return LLMResponse(
            content=r.get("content", ""),
            tool_calls=tool_calls,
            tokens_in=r.get("tokens_in", 0),
            tokens_out=r.get("tokens_out", 0),
            finish_reason="tool_use" if tool_calls else "end_turn",
            raw=r,
        )

    def estimate_tokens(self, request: LLMRequest) -> int:
        return max(1, len(_request_text(request)) // 4)
