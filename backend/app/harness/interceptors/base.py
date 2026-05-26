"""Interceptors are the cross-cutting cousins of validators: they run before and
after every call regardless of provider or content. The seam where cost caps,
PII redaction, tracing, recording, and eval hooks plug in."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.harness.call import HarnessedCall, LLMRequest


@dataclass
class InterceptorDecision:
    action: Literal["continue", "block", "modify"] = "continue"
    reason: str | None = None
    modified_request: LLMRequest | None = None


@runtime_checkable
class Interceptor(Protocol):
    name: str

    async def before(self, call: HarnessedCall) -> InterceptorDecision: ...

    async def after(self, call: HarnessedCall) -> None: ...
