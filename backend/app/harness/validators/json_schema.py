"""Validates that a JSON-mode response parses and satisfies required keys.

Minimal dependency-free check (parse + required-key presence). Production swaps
in `jsonschema` for full schema validation; the interface is unchanged.
"""

from __future__ import annotations

import json

from app.harness.call import LLMRequest, Message, LLMResponse, ValidationResult


class JSONSchemaValidator:
    name = "json_schema"
    allows_retry = True

    def __init__(self, schema: dict | None = None):
        self.schema = schema or {}

    def validate(self, response: LLMResponse, request: LLMRequest) -> ValidationResult:
        try:
            parsed = json.loads(response.content)
        except (json.JSONDecodeError, TypeError) as exc:
            return ValidationResult(self.name, passed=False, detail=f"not valid JSON: {exc}")

        required = self.schema.get("required", [])
        missing = [k for k in required if k not in parsed]
        if missing:
            return ValidationResult(
                self.name, passed=False, detail=f"missing required keys: {missing}"
            )
        return ValidationResult(self.name, passed=True)

    def reinject(self, request: LLMRequest, result: ValidationResult) -> LLMRequest:
        request.messages.append(
            Message(
                role="user",
                content=(
                    f"Your previous output failed validation: {result.detail}. "
                    f"Respond with valid JSON"
                    + (f" including keys {self.schema['required']}." if self.schema.get("required") else ".")
                ),
            )
        )
        return request
