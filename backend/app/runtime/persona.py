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

    return "\n\n".join(parts)
