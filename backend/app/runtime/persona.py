"""Compose an agent's effective system prompt from its identity layers.

Order matters: soul (who it is) -> persona (how it behaves) -> role (its job in
this workflow) -> system_prompt (task instructions). The soul is the stable
identity that an external memory layer (extremis) accretes episodic memory around.
"""

from __future__ import annotations

from typing import Any


def compose_system_prompt(agent: dict[str, Any]) -> str:
    parts: list[str] = []

    soul = (agent.get("soul_md") or "").strip()
    if soul:
        parts.append(f"# Who you are\n{soul}")

    persona = agent.get("persona") or {}
    persona_lines: list[str] = []
    if persona.get("traits"):
        persona_lines.append("Personality: " + ", ".join(persona["traits"]))
    if persona.get("tone"):
        persona_lines.append(f"Tone: {persona['tone']}")
    if persona.get("values"):
        persona_lines.append("Values: " + ", ".join(persona["values"]))
    if persona.get("speaking_style"):
        persona_lines.append(f"Speaking style: {persona['speaking_style']}")
    if persona_lines:
        parts.append("# How you behave\n" + "\n".join(persona_lines))

    if agent.get("role"):
        parts.append(f"# Your role\n{agent['role']}")

    if agent.get("system_prompt"):
        parts.append(f"# Instructions\n{agent['system_prompt']}")

    # If this agent can collaborate, tell it so — so it actually reaches out to
    # teammates and escalates instead of refusing work outside its lane.
    tool_names = {t.get("name") for t in (agent.get("tool_schemas") or [])}
    if "send_message_to_agent" in tool_names:
        parts.append(
            "# Working as a team\n"
            "You're part of a team of agents. If a request needs information or work "
            "outside your expertise, don't refuse — use `send_message_to_agent` to ask "
            "the right teammate by their exact name (use `list_agents` to see who's "
            "available), then use their reply. For anything big, ambiguous, or "
            "cross-functional, escalate to `Jarvis` (the chief of staff). Collaborate "
            "like a real colleague."
        )

    return "\n\n".join(parts)
