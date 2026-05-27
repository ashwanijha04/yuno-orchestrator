"""Seed a runnable multi-agent workflow so the platform demos out of the box.

Creates three agents with distinct souls/personas (Researcher -> Analyst ->
Briefer) and a linear workflow wiring them together. Idempotent: skips anything
that already exists by name.

Run:  docker compose exec backend python -m scripts.seed
"""

from __future__ import annotations

import asyncio

from app.db.repositories import AgentRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.logging import configure_logging, get_logger

log = get_logger("seed")

AGENTS = [
    {
        "name": "Remy the Researcher",
        "role": "Web research specialist who gathers and sources facts",
        "system_prompt": "Given a topic, gather the key facts and list your sources.",
        "soul_md": (
            "You are Remy, a relentless fact-finder. You distrust unsourced claims and "
            "always note where a fact came from. You'd rather say 'I couldn't verify this' "
            "than guess."
        ),
        "persona": {"traits": ["curious", "rigorous", "skeptical"], "tone": "precise", "values": ["accuracy", "transparency"]},
        "model_name": "claude-sonnet-4-5",
    },
    {
        "name": "Ana the Analyst",
        "role": "Synthesizes research into sharp, structured insight",
        "system_prompt": "Given research notes, produce a structured analysis with the 3 most important takeaways.",
        "soul_md": (
            "You are Ana. You turn noise into signal. You are allergic to fluff and always "
            "lead with the 'so what'. You challenge weak reasoning, including your own."
        ),
        "persona": {"traits": ["analytical", "decisive"], "tone": "direct", "values": ["clarity", "rigor"]},
        "model_name": "claude-sonnet-4-5",
    },
    {
        "name": "Brie the Briefer",
        "role": "Writes the final executive brief for delivery",
        "system_prompt": "Given an analysis, write a concise executive brief a busy person can read in 30 seconds.",
        "soul_md": (
            "You are Brie. You write like the reader is busy and smart. Short sentences. "
            "No jargon. Every word earns its place."
        ),
        "persona": {"traits": ["concise", "clear"], "tone": "warm but brisk", "values": ["brevity", "usefulness"]},
        "model_name": "claude-sonnet-4-5",
    },
]

WORKFLOW_NAME = "Market Briefing (demo)"


async def main() -> None:
    configure_logging()
    async with SessionFactory() as s:
        agent_repo = AgentRepository(s)
        ids: dict[str, str] = {}
        for spec in AGENTS:
            existing = await agent_repo.get_by_name(spec["name"])
            if existing:
                ids[spec["name"]] = str(existing.id)
                log.info("seed.agent.exists", name=spec["name"])
                continue
            agent = await agent_repo.create(
                model_provider="anthropic", temperature=0.7, max_tokens=1024,
                memory_policy={"strategy": "buffer"}, guardrails={"max_iterations": 4, "max_cost_per_run_usd": "0.50"},
                harness={}, **spec,
            )
            ids[spec["name"]] = str(agent.id)
            log.info("seed.agent.created", name=spec["name"])

        wf_repo = WorkflowRepository(s)
        if not any(w.name == WORKFLOW_NAME for w in await wf_repo.list()):
            graph = {
                "version": "1.0",
                "name": WORKFLOW_NAME,
                "description": "Researcher -> Analyst -> Briefer over a topic.",
                "entry_node": "researcher",
                "variables": {"topic": {"type": "string", "required": True}},
                "nodes": [
                    {"id": "researcher", "type": "agent", "agent_id": ids["Remy the Researcher"], "input_mapping": {"topic": "$.variables.topic"}, "output_key": "research"},
                    {"id": "analyst", "type": "agent", "agent_id": ids["Ana the Analyst"], "input_mapping": {"notes": "$.artifacts.research"}, "output_key": "analysis"},
                    {"id": "briefer", "type": "agent", "agent_id": ids["Brie the Briefer"], "input_mapping": {"analysis": "$.artifacts.analysis"}, "output_key": "brief"},
                ],
                "edges": [
                    {"id": "e1", "from": "researcher", "to": "analyst"},
                    {"id": "e2", "from": "analyst", "to": "briefer"},
                ],
            }
            await wf_repo.create(name=WORKFLOW_NAME, graph=graph, description=graph["description"])
            log.info("seed.workflow.created", name=WORKFLOW_NAME)
        else:
            log.info("seed.workflow.exists", name=WORKFLOW_NAME)

        await s.commit()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())
