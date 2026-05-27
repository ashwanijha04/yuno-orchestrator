"""AgentRuntime — a typed, ready-to-run view of an Agent row.

Built once from the ORM model (which lives only inside a DB session), then carried
through the runtime so node execution never touches the ORM or passes loose dicts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.db.models import Agent
from app.tools.registry import schemas_for


@dataclass
class AgentRuntime:
    id: uuid.UUID
    name: str
    role: str
    system_prompt: str
    soul_md: str | None
    persona: dict[str, Any]
    model_provider: str
    model_name: str
    task_type: str
    temperature: float
    max_tokens: int
    guardrails: dict[str, Any]
    harness: dict[str, Any]
    memory_policy: dict[str, Any] = field(default_factory=dict)
    tool_ids: list[str] = field(default_factory=list)
    tool_schemas: list[dict] = field(default_factory=list)

    @classmethod
    def from_model(cls, agent: Agent) -> AgentRuntime:
        tool_ids = list(agent.tool_ids or [])
        return cls(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            system_prompt=agent.system_prompt,
            soul_md=agent.soul_md,
            persona=agent.persona or {},
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            task_type=agent.task_type or "auto",
            temperature=float(agent.temperature),
            max_tokens=agent.max_tokens,
            guardrails=agent.guardrails or {},
            harness=agent.harness or {},
            memory_policy=agent.memory_policy or {},
            tool_ids=tool_ids,
            # Advertise the granted tools' schemas to the LLM (executed by the
            # ToolRuntime wired into the engine).
            tool_schemas=schemas_for(tool_ids),
        )

    def as_dict(self) -> dict[str, Any]:
        """Dict view consumed by the inner loop + prompt composition."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "soul_md": self.soul_md,
            "persona": self.persona,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "task_type": self.task_type,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "guardrails": self.guardrails,
            "harness": self.harness,
            "memory_policy": self.memory_policy,
            "tool_schemas": self.tool_schemas,
        }
