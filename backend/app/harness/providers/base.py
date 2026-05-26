"""LLMProvider protocol + error taxonomy.

This is the ONLY layer that knows provider-specific shapes. Everything above
(executor, interceptors, validators) sees normalized `LLMRequest`/`LLMResponse`.
Never write `if provider == "x":` outside a provider module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.harness.call import LLMRequest, LLMResponse


class RetryableError(Exception):
    """Transient failure (timeout, 429). The executor retries with backoff."""


class FatalError(Exception):
    """Non-retryable failure (auth, bad request). Propagates immediately."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    supports_images: bool

    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    def estimate_tokens(self, request: LLMRequest) -> int:
        """Conservative (round-up) pre-call token estimate for the cost cap."""
        ...
