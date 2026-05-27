"""Tool registry — the catalog of tools an agent can be granted (by `tool_ids`).

Definitions live here so the UI can offer a real multiselect; execution wiring
lands in Phase 5. Each entry is the JSON Schema the LLM sees plus metadata.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict
    requires_approval: bool = False


TOOL_DEFS: dict[str, ToolDef] = {
    "web_search": ToolDef(
        "web_search",
        "Search the web for current information.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "http_request": ToolDef(
        "http_request",
        "Make an allowlisted HTTP GET/POST request.",
        {"type": "object", "properties": {"method": {"type": "string"}, "url": {"type": "string"}}, "required": ["url"]},
    ),
    "send_message_to_agent": ToolDef(
        "send_message_to_agent",
        "Delegate a subtask to another agent by its exact name. Runs that agent and returns its reply.",
        {"type": "object", "properties": {"recipient": {"type": "string"}, "content": {"type": "string"}}, "required": ["recipient", "content"]},
    ),
    "list_agents": ToolDef(
        "list_agents",
        "List the existing agents (name + role) so you can reuse one instead of creating a duplicate.",
        {"type": "object", "properties": {}},
    ),
    "create_agent": ToolDef(
        "create_agent",
        "Create a new specialist agent when no existing agent fits. Returns its name so you can immediately delegate to it.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Unique, descriptive agent name, e.g. 'Market Researcher'"},
                "role": {"type": "string", "description": "One-line description of what this agent does"},
                "system_prompt": {"type": "string", "description": "Instructions / personality for the agent"},
                "task_type": {"type": "string", "enum": ["coding", "normal", "conversation"], "description": "Routes to the best model"},
                "tool_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional worker tools: web_search, http_request, send_to_channel, python_exec"},
            },
            "required": ["name", "role"],
        },
    ),
    "send_to_channel": ToolDef(
        "send_to_channel",
        "Send a message to an external channel (e.g. Telegram).",
        {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
    ),
    "python_exec": ToolDef(
        "python_exec",
        "Run a short Python snippet in an isolated sandbox.",
        {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        requires_approval=True,
    ),
}


def list_tools() -> list[ToolDef]:
    return list(TOOL_DEFS.values())


def schemas_for(tool_ids: list[str]) -> list[dict]:
    """Tool JSON schemas (Anthropic tool format) for the agent's granted tools."""
    out = []
    for tid in tool_ids:
        td = TOOL_DEFS.get(tid)
        if td:
            out.append({"name": td.name, "description": td.description, "input_schema": td.input_schema})
    return out
