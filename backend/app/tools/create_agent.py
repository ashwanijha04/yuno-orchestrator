"""create_agent — lets an orchestrator spin up a new specialist agent at runtime.

This is what makes the platform genuinely agentic: when no existing agent fits a
subtask, the orchestrator creates one (name + role + instructions), then delegates
to it via send_message_to_agent. Idempotent by name so retries don't duplicate.

Created agents never receive the orchestration tools (create_agent /
send_message_to_agent) — that prevents runaway recursion (an agent spawning agents
spawning agents). They may be granted the safe worker tools only.
"""

from __future__ import annotations

from app.db.repositories import AgentRepository
from app.tools.base import ToolContext

# Tools a spawned worker may hold; orchestration tools are deliberately excluded.
_ALLOWED_WORKER_TOOLS = {"web_search", "http_request", "send_to_channel", "python_exec"}
_TASK_TYPES = {"coding", "normal", "conversation", "auto"}


class CreateAgentTool:
    name = "create_agent"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        name = str(input.get("name", "")).strip()
        role = str(input.get("role", "")).strip()
        if not name or not role:
            return {"error": "name and role are required"}

        system_prompt = str(input.get("system_prompt") or f"You are {name}. {role}").strip()
        task_type = str(input.get("task_type") or "normal")
        if task_type not in _TASK_TYPES:
            task_type = "normal"
        requested = input.get("tool_ids") or []
        tool_ids = [t for t in requested if t in _ALLOWED_WORKER_TOOLS]

        async with ctx.session_factory() as s:
            repo = AgentRepository(s)
            existing = await repo.get_by_name(name)
            if existing:
                return {
                    "status": "exists", "id": str(existing.id), "name": existing.name,
                    "note": "an agent with this name already exists — reuse it",
                }
            agent = await repo.create(
                name=name,
                role=role,
                system_prompt=system_prompt,
                model_provider="openai",
                model_name="gpt-4o-mini",
                task_type=task_type,
                tool_ids=tool_ids,
                memory_policy={"strategy": "buffer"},
                guardrails={"max_iterations": 6, "max_cost_per_run_usd": "0.50"},
                harness={},
            )
            await s.commit()
            return {
                "status": "created", "id": str(agent.id), "name": agent.name,
                "note": "now delegate to it with send_message_to_agent using this exact name",
            }
