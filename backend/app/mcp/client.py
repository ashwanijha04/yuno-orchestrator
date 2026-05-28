"""MCP client — connects to configured MCP servers, lists their tools, and
invokes them. Connect-per-call (spawn → initialise → call → tear down) keeps it
robust with no long-lived session state across the async app.

Configured servers live in MCP_SERVERS. Adding a server = one entry here (or, in
production, a row/env) — no other code changes. Tools surface to agents as
`mcp__<server>__<tool>`.
"""

from __future__ import annotations

import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.logging import get_logger

log = get_logger("mcp")

# The demo server ships with the platform; others can be added here.
MCP_SERVERS: dict[str, StdioServerParameters] = {
    "demo": StdioServerParameters(command=sys.executable, args=["-m", "app.mcp.demo_server"]),
}


async def list_server_tools(server: str) -> list[dict]:
    """[{name, description, input_schema}] for one server's tools."""
    params = MCP_SERVERS.get(server)
    if params is None:
        return []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema or {}}
                for t in result.tools
            ]


async def call(server: str, tool: str, arguments: dict) -> dict:
    """Invoke an MCP tool; returns {result: str} or {error: str}."""
    params = MCP_SERVERS.get(server)
    if params is None:
        return {"error": f"unknown MCP server {server!r}"}
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool(tool, arguments or {})
                text = "\n".join(getattr(c, "text", str(c)) for c in (res.content or []))
                return {"result": text}
    except Exception as exc:  # noqa: BLE001 — surface as a tool result the LLM can react to
        log.warning("mcp.call_failed", server=server, tool=tool, detail=str(exc))
        return {"error": f"MCP call failed: {exc}"}


async def discover() -> dict[str, list[dict]]:
    """All configured servers → their tools. Best-effort (skips unreachable)."""
    out: dict[str, list[dict]] = {}
    for name in MCP_SERVERS:
        try:
            out[name] = await list_server_tools(name)
        except Exception as exc:  # noqa: BLE001
            log.warning("mcp.discover_failed", server=name, detail=str(exc))
            out[name] = []
    return out
