"""Core harness value types: requests, responses, content blocks, and the
per-invocation `HarnessedCall` transaction object.

Content blocks are typed (text | image) from the start so multimodal (Phase 6)
slots in without reshaping the request — only providers learn to encode images.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


# ── Content blocks ───────────────────────────────────────────────────────────


@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImageBlock:
    mime: str
    data: str | None = None          # base64; or
    media_ref: str | None = None     # reference into media_assets (recordings)
    type: Literal["image"] = "image"


ContentBlock = TextBlock | ImageBlock
MessageContent = str | list[ContentBlock]


@dataclass
class Message:
    role: str  # system | user | assistant | tool
    content: MessageContent


# ── Request / response ───────────────────────────────────────────────────────


@dataclass
class LLMRequest:
    model_provider: str
    model_name: str
    messages: list[Message] = field(default_factory=list)
    system: str | None = None
    tools: list[dict] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 2048
    response_format: Literal["text", "json"] = "text"
    metadata: dict[str, Any] = field(default_factory=dict)  # agent_id, run_id, ...

    def has_images(self) -> bool:
        for m in self.messages:
            if isinstance(m.content, list) and any(
                isinstance(b, ImageBlock) for b in m.content
            ):
                return True
        return False


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0          # uncached input tokens (full price)
    tokens_out: int = 0
    finish_reason: str | None = None
    raw: dict = field(default_factory=dict)
    # Prompt-cache usage (Anthropic ephemeral cache). cache_read = hit (10%);
    # cache_creation = miss that *wrote* the cache (125%). Zero when caching is
    # disabled or unsupported by the provider.
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


# ── Attempt + harnessed call ─────────────────────────────────────────────────


@dataclass
class ValidationResult:
    validator: str
    passed: bool
    detail: str | None = None


@dataclass
class Attempt:
    num: int
    started_at: datetime
    raw_response: dict | None = None
    error: str | None = None
    validation_failures: list[str] = field(default_factory=list)
    latency_ms: int = 0


@dataclass
class BudgetTracker:
    """Running cost accounting for a single run, consulted by CostCap."""

    cap_usd: Decimal | None = None
    spent_usd: Decimal = Decimal("0")

    def would_exceed(self, additional: Decimal) -> bool:
        if self.cap_usd is None:
            return False
        return (self.spent_usd + additional) > self.cap_usd

    def add(self, amount: Decimal) -> None:
        self.spent_usd += amount


@dataclass
class ProviderCandidate:
    """One (provider, model) the executor may try. Ordered candidates form the
    model-routing fallback chain."""

    provider: Any  # LLMProvider
    model_name: str
    cost_model: Any  # CostModel


@dataclass
class HarnessedCall:
    request: LLMRequest
    provider: Any  # LLMProvider — the active candidate (set by the executor)
    cost_model: Any  # CostModel — the active candidate's
    validators: list[Any] = field(default_factory=list)
    interceptors: list[Any] = field(default_factory=list)
    budget: BudgetTracker = field(default_factory=BudgetTracker)
    max_attempts: int = 3
    # Ordered fallback chain; if empty the executor uses `provider`/`cost_model`.
    candidates: list[ProviderCandidate] = field(default_factory=list)

    call_id: uuid.UUID = field(default_factory=uuid.uuid4)
    run_id: uuid.UUID | None = None
    step_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None

    response: LLMResponse | None = None
    attempts: list[Attempt] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)
    cost_usd: Decimal = Decimal("0")
    blocked_reason: str | None = None
