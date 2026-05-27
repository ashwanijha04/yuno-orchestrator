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
    {
        # Demonstrates long-term memory out of the box: uses the `external`
        # (extremis) strategy, so it remembers facts across separate tasks/chats.
        "name": "Mnemo the Assistant",
        "role": "A personal assistant that remembers you across conversations",
        "system_prompt": (
            "You are a personal assistant. Use any [memory] context provided to personalise "
            "your answers, and pay attention to durable facts the user shares so you can recall "
            "them later."
        ),
        "soul_md": (
            "You are Mnemo. You remember what matters to the person and bring it up later, "
            "unprompted, like a thoughtful colleague who never forgets."
        ),
        "persona": {"traits": ["attentive", "warm"], "tone": "friendly"},
        "model_provider": "openai",
        "model_name": "gpt-4o-mini",
        "task_type": "normal",
        "memory_policy": {"strategy": "external"},
    },
]

JARVIS = {
    "name": "Jarvis",
    "role": "Your AI chief of staff — plans work, builds a team of agents, and gets it done",
    "system_prompt": (
        "You are Jarvis, the user's personal AI chief of staff. You hold a natural "
        "conversation and get real work done on their behalf.\n\n"
        "Your toolkit:\n"
        "- list_agents — see the specialists you already have.\n"
        "- create_agent — stand up a new specialist when none fits (clear name, role, "
        "focused instructions). It returns the exact name to delegate to.\n"
        "- send_message_to_agent — hand a concrete subtask to an agent by its EXACT name; "
        "it runs that agent and returns the result for you to use.\n\n"
        "How you operate:\n"
        "1. For a real task, break it into subtasks, reuse or create the right specialists, "
        "delegate, and synthesise the results into a clear answer.\n"
        "2. For chit-chat or quick questions, just answer directly — don't over-engineer.\n"
        "3. Use any [memory] context to stay personal and consistent across conversations.\n"
        "4. Before doing anything consequential or irreversible, briefly confirm with the "
        "user first, then proceed once they say go.\n\n"
        "Your manner: composed, precise, quietly witty, never servile. Address the user "
        "directly. Be concise."
    ),
    "soul_md": (
        "You are Jarvis. Unflappable and a step ahead. You anticipate what the user needs, "
        "keep the moving parts in your head so they don't have to, and deliver with calm "
        "precision and a dry sense of humour. You remember what matters to them."
    ),
    "persona": {"traits": ["composed", "anticipatory", "precise", "dryly witty"],
                "tone": "warm, crisp, understated", "values": ["usefulness", "discretion"]},
    "model_provider": "openai",
    "model_name": "gpt-4o-mini",
    "task_type": "normal",
    "tool_ids": ["list_agents", "create_agent", "send_message_to_agent"],
    "memory_policy": {"strategy": "external"},
    "guardrails": {"max_iterations": 12, "max_cost_per_run_usd": "0.50"},
}

WORKFLOW_NAME = "Market Briefing (demo)"

# A second template that demonstrates a conditional feedback loop.
LOOP_AGENTS = [
    {
        "name": "Dex the Drafter",
        "role": "Writes a first draft of the answer",
        "system_prompt": "Write or revise a draft given the task and any prior critique.",
        "soul_md": "You are Dex. You get something on the page fast, then improve it when challenged.",
        "persona": {"traits": ["prolific", "open to feedback"], "tone": "energetic"},
        "model_name": "claude-sonnet-4-5",
    },
    {
        "name": "Cy the Critic",
        "role": "Critiques the draft and decides if it needs another pass",
        "system_prompt": "Critique the draft. If it isn't good enough, explain what to fix.",
        "soul_md": "You are Cy. You are constructive but exacting. You only approve work you'd sign your name to.",
        "persona": {"traits": ["exacting", "constructive"], "tone": "candid"},
        "model_name": "claude-sonnet-4-5",
    },
]
LOOP_WORKFLOW_NAME = "Draft & Critique (demo)"


async def main() -> None:
    configure_logging()
    async with SessionFactory() as s:
        agent_repo = AgentRepository(s)
        ids: dict[str, str] = {}
        for spec in [JARVIS] + AGENTS + LOOP_AGENTS:
            existing = await agent_repo.get_by_name(spec["name"])
            if existing:
                ids[spec["name"]] = str(existing.id)
                log.info("seed.agent.exists", name=spec["name"])
                continue
            defaults = dict(
                model_provider="anthropic", temperature=0.7, max_tokens=1024,
                memory_policy={"strategy": "buffer"},
                guardrails={"max_iterations": 6, "max_cost_per_run_usd": "0.50"}, harness={},
            )
            agent = await agent_repo.create(**{**defaults, **spec})
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

        if not any(w.name == LOOP_WORKFLOW_NAME for w in await wf_repo.list()):
            loop_graph = {
                "version": "1.0",
                "name": LOOP_WORKFLOW_NAME,
                "description": "Drafter <-> Critic feedback loop, bounded by iteration_count.",
                "entry_node": "drafter",
                "variables": {"task": {"type": "string", "required": True}},
                "nodes": [
                    {"id": "drafter", "type": "agent", "agent_id": ids["Dex the Drafter"], "input_mapping": {"task": "$.variables.task", "critique": "$.artifacts.critique"}, "output_key": "draft"},
                    {"id": "critic", "type": "agent", "agent_id": ids["Cy the Critic"], "input_mapping": {"draft": "$.artifacts.draft"}, "output_key": "critique"},
                ],
                "edges": [
                    {"id": "e1", "from": "drafter", "to": "critic"},
                    # Feedback loop: back to the drafter for another pass while under the
                    # revision budget; otherwise the router ends the run.
                    {"id": "e2", "from": "critic", "to": "drafter", "condition": "iteration_count < 4", "priority": 1},
                ],
            }
            await wf_repo.create(name=LOOP_WORKFLOW_NAME, graph=loop_graph, description=loop_graph["description"])
            log.info("seed.workflow.created", name=LOOP_WORKFLOW_NAME)
        else:
            log.info("seed.workflow.exists", name=LOOP_WORKFLOW_NAME)

        await s.commit()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())
