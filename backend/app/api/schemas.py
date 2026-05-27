"""Pydantic request/response models. The frontend's TS types are generated from
the OpenAPI these produce, so there are no hand-maintained DTOs on the client."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class Persona(BaseModel):
    traits: list[str] = Field(default_factory=list)
    tone: str | None = None
    values: list[str] = Field(default_factory=list)
    speaking_style: str | None = None


class AgentCreate(BaseModel):
    name: str
    role: str
    system_prompt: str
    soul_md: str | None = None
    persona: dict[str, Any] = Field(default_factory=dict)
    model_provider: str = "anthropic"
    model_name: str = "claude-sonnet-4-6"
    temperature: float = 0.7
    max_tokens: int = 2048
    tool_ids: list[str] = Field(default_factory=list)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    guardrails: dict[str, Any] = Field(default_factory=dict)
    harness: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    role: str | None = None
    system_prompt: str | None = None
    soul_md: str | None = None
    persona: dict[str, Any] | None = None
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tool_ids: list[str] | None = None
    memory_policy: dict[str, Any] | None = None
    guardrails: dict[str, Any] | None = None
    harness: dict[str, Any] | None = None


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    system_prompt: str
    soul_md: str | None
    persona: dict[str, Any]
    model_provider: str
    model_name: str
    temperature: float
    max_tokens: int
    tool_ids: list[str]
    memory_policy: dict[str, Any]
    guardrails: dict[str, Any]
    harness: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    current_version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowDetail(WorkflowOut):
    graph: dict[str, Any]


class RunWorkflowRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    max_cost_usd: Decimal | None = None


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    graph: dict[str, Any]


class WorkflowSaveVersion(BaseModel):
    graph: dict[str, Any]


class ValidateRequest(BaseModel):
    graph: dict[str, Any]


class ValidationIssueOut(BaseModel):
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class ValidateResponse(BaseModel):
    valid: bool
    issues: list[ValidationIssueOut]


class QuickRunRequest(BaseModel):
    """Run a single agent as a synthetic one-node workflow (the simplest path
    to a live run while the visual builder is still being built)."""

    input: str
    max_cost_usd: Decimal | None = None


class ChannelCreate(BaseModel):
    type: str  # telegram | slack | whatsapp
    name: str
    config: dict[str, Any] = Field(default_factory=dict)  # {bot_token, webhook_secret}


class ChannelOut(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BindingCreate(BaseModel):
    agent_id: uuid.UUID | None = None
    workflow_id: uuid.UUID | None = None
    external_id: str  # chat id / channel id
    config: dict[str, Any] = Field(default_factory=dict)


class BindingOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    channel_id: uuid.UUID
    workflow_id: uuid.UUID | None
    external_id: str

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version: int
    status: str
    trigger_type: str
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: Decimal
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class StepOut(BaseModel):
    id: uuid.UUID
    node_id: str
    agent_id: uuid.UUID | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    cost_usd: Decimal
    tokens_in: int
    tokens_out: int
    error: str | None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    recipient_agent_id: uuid.UUID | None
    role: str
    content: str
    tool_calls: list[dict] | dict | None
    cost_usd: Decimal
    tokens_in: int
    tokens_out: int
    ts: datetime

    model_config = {"from_attributes": True}


class RunDetail(RunOut):
    steps: list[StepOut]
    messages: list[MessageOut]
