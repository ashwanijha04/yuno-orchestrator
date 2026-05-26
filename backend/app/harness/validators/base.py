"""Validators sit between the raw provider response and the rest of the system.
They pass, fail, or fail-with-retry. A failing validator that `allows_retry`
reinjects a corrective message and the executor tries again."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.harness.call import LLMRequest, LLMResponse, ValidationResult


@runtime_checkable
class Validator(Protocol):
    name: str
    allows_retry: bool

    def validate(self, response: LLMResponse, request: LLMRequest) -> ValidationResult: ...

    def reinject(self, request: LLMRequest, result: ValidationResult) -> LLMRequest:
        """Return a (possibly modified) request for the retry attempt."""
        ...
