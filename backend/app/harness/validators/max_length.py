"""Truncates runaway outputs. Never fails the call — it trims in place and logs."""

from __future__ import annotations

from app.harness.call import LLMRequest, LLMResponse, ValidationResult


class MaxLengthValidator:
    name = "max_length"
    allows_retry = False

    def __init__(self, max_chars: int = 10_000):
        self.max_chars = max_chars

    def validate(self, response: LLMResponse, request: LLMRequest) -> ValidationResult:
        if len(response.content) > self.max_chars:
            response.content = response.content[: self.max_chars]
            return ValidationResult(
                self.name, passed=True, detail=f"truncated to {self.max_chars} chars"
            )
        return ValidationResult(self.name, passed=True)

    def reinject(self, request: LLMRequest, result: ValidationResult) -> LLMRequest:
        return request
