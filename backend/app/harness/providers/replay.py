"""Replays previously recorded real LLM calls, in sequence, for deterministic
offline demos and tests. Image calls reference media_assets rather than inlining
bytes, so replay stays cheap and byte-stable."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.harness.call import LLMRequest, LLMResponse, ToolCall


@dataclass
class RecordedCall:
    request: dict
    response: dict
    latency_ms: int = 0


class ReplayExhaustedError(Exception):
    pass


class ReplayProvider:
    name = "replay"
    supports_images = True

    def __init__(self, calls: list[RecordedCall], speed_factor: float = 0.0):
        # speed_factor 0 = instant (tests); 1.0 = original latency (demos).
        self._calls = calls
        self._cursor = 0
        self.speed_factor = speed_factor

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._cursor >= len(self._calls):
            raise ReplayExhaustedError("no more recorded calls to replay")
        recorded = self._calls[self._cursor]
        self._cursor += 1

        if self.speed_factor > 0 and recorded.latency_ms:
            await asyncio.sleep(recorded.latency_ms / 1000 * self.speed_factor)

        r = recorded.response
        tool_calls = [
            ToolCall(id=tc.get("id", f"tc_{i}"), name=tc["name"], input=tc.get("input", {}))
            for i, tc in enumerate(r.get("tool_calls", []))
        ]
        return LLMResponse(
            content=r.get("content", ""),
            tool_calls=tool_calls,
            tokens_in=r.get("tokens_in", 0),
            tokens_out=r.get("tokens_out", 0),
            finish_reason=r.get("finish_reason"),
            raw=r,
        )

    def estimate_tokens(self, request: LLMRequest) -> int:
        return 0
