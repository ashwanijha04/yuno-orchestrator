"""list_agents — lets an orchestrator see the current roster so it reuses an
existing specialist instead of creating a duplicate."""

from __future__ import annotations

from app.db.repositories import AgentRepository
from app.tools.base import ToolContext

# Don't advertise the orchestrators themselves as delegation targets.
_HIDDEN = {"Orchestrator"}


class ListAgentsTool:
    name = "list_agents"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        async with ctx.session_factory() as s:
            agents = await AgentRepository(s).list()
        roster = [
            {"name": a.name, "role": a.role}
            for a in agents
            if a.name not in _HIDDEN
        ]
        return {"agents": roster, "count": len(roster)}
