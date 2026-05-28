"""ToolRuntime — dispatches a tool call by name and executes it with a
ToolContext. Passed into the inner loop; the loop persists the result as a
tool message (so tool calls show on the timeline)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.logging import get_logger
from app.tools.base import Tool, ToolContext
from app.tools.coding import CodingSessionTool
from app.tools.create_agent import CreateAgentTool
from app.tools.debate import RunDebateTool
from app.tools.http_request import HttpRequestTool
from app.tools.list_agents import ListAgentsTool
from app.tools.python_exec import PythonExecTool
from app.tools.send_to_agent import SendToAgentTool
from app.tools.send_to_channel import SendToChannelTool
from app.tools.web_search import WebSearchTool

log = get_logger("tools")


class ToolRuntime:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        impls: list[Tool] = [
            WebSearchTool(), HttpRequestTool(), SendToAgentTool(),
            SendToChannelTool(), PythonExecTool(),
            CreateAgentTool(), ListAgentsTool(), RunDebateTool(), CodingSessionTool(),
        ]
        self.tools = {t.name: t for t in impls}

    async def __call__(self, name: str, input: dict, ctx: dict) -> dict:
        # MCP tools (mcp__<server>__<tool>) route to the MCP client.
        if name.startswith("mcp__"):
            from app.mcp import client as mcp_client

            parts = name.split("__", 2)
            if len(parts) == 3:
                return await mcp_client.call(parts[1], parts[2], input)
            return {"error": f"malformed MCP tool name {name!r}"}

        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name!r}"}
        run_id = ctx.get("run_id")
        agent_id = ctx.get("agent_id")
        context = ToolContext(
            run_id=uuid.UUID(run_id) if isinstance(run_id, str) else run_id,
            agent_id=uuid.UUID(agent_id) if isinstance(agent_id, str) else agent_id,
            session_factory=self.session_factory,
        )
        try:
            return await tool.execute(input, context)
        except Exception as exc:  # noqa: BLE001 — tool errors become results the LLM can react to
            log.warning("tool.error", tool=name, detail=str(exc))
            return {"error": str(exc)}
