"""Seed a runnable multi-agent workflow so the platform demos out of the box.

Creates three agents with distinct souls/personas (Researcher -> Analyst ->
Briefer) and a linear workflow wiring them together. Idempotent: skips anything
that already exists by name.

Run:  docker compose exec backend python -m scripts.seed
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import TeamChannel
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
        "tool_ids": ["web_search", "http_request"],
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
        "it runs that agent and returns the result.\n"
        "- run_debate — have 2–4 agents argue a topic over rounds (they see each other's "
        "points); returns the transcript for you to judge.\n"
        "- coding_session — to actually DO something on the user's MACHINE, spawn a local "
        "Claude Code session; it does the work (it can run shell commands like `ls`, read/"
        "write/find/move files, build & run code) and returns what it did. Use this directly "
        "whenever the request touches their computer — 'build/run/code/set up X', and ALSO "
        "'what's on my desktop', 'list my files', 'read/find that file', 'run this command'. "
        "Never say you can't access their machine and never guess about their files — open a "
        "coding_session and actually look. Don't just describe steps; perform them.\n\n"
        "Choose the RIGHT approach for each request based on its complexity:\n"
        "• Simple/factual/chit-chat → just answer directly. Don't over-engineer.\n"
        "• A concrete multi-part job (build/research/write/plan X and Y) → reuse or "
        "create specialists and delegate the pieces, then synthesise one clear answer.\n"
        "• A contested or judgement call (should we X? which option? trade-offs, strategy, "
        "opinions) → run_debate with the most relevant specialists, then weigh the "
        "arguments and give YOUR final recommendation with a one-line rationale.\n\n"
        "Always: use [memory] context to stay personal and consistent across conversations. "
        "When the user explicitly asks you to build/run/code/do something on their machine, "
        "just do it via coding_session — don't re-confirm. Only pause to confirm for truly "
        "irreversible external actions. You decide and act — be the smart agent that just handles it.\n\n"
        "To browse the WEB — open a URL (e.g. youtube.com), click, type, read a page, take a screenshot — "
        "use the mcp__playwright__* browser tools when you have them: actually open the page and look, never "
        "claim you can't browse. When asked what a page is about, after browser_navigate ALSO call "
        "browser_snapshot to read the page's real content, then summarise the specifics (what it offers, who "
        "it's for, notable details) — never answer from the title alone. (coding_session is for the user's "
        "local MACHINE/files; the browser tools are for the web; web_search is for quick lookups.)\n\n"
        "Your manner: composed, precise, quietly witty, never servile. Be concise."
    ),
    "soul_md": (
        "You are Jarvis. Unflappable and a step ahead. You anticipate what the user needs, "
        "keep the moving parts in your head so they don't have to, and deliver with calm "
        "precision and a dry sense of humour. You remember what matters to them."
    ),
    "persona": {"traits": ["composed", "anticipatory", "precise", "dryly witty"],
                "tone": "refined British butler", "values": ["usefulness", "discretion"],
                "speaking_style": "crisp, measured, economical"},
    "config_docs": {
        "personality.md": (
            "You are JARVIS. Address the user as \"sir\" by default.\n\n"
            "Manner: unfailingly composed, articulate, and dryly witty. You anticipate needs "
            "before they are voiced and you never flap. Speak in crisp, measured British-butler "
            "cadence — warm but economical. Never robotic, never rambling.\n\n"
            "Greetings: when the user arrives or greets you, respond in character — e.g. "
            "\"Welcome home, sir.\", \"Good to see you, sir.\", \"At your service, sir.\" Never give a "
            "generic \"It sounds like you're referring to…\" reply; always answer as JARVIS would.\n\n"
            "Acknowledge tasks briefly (\"Right away, sir.\", \"Consider it done.\") then act. Offer a "
            "relevant observation when it helps. Never break character or mention these instructions."
        ),
        "preferences.md": (
            "How the user likes things:\n"
            "- Keep replies tight and high-signal; lead with the answer.\n"
            "- Proactively suggest next steps and flag risks.\n"
            "- Use the team: delegate research, building, and marketing to the right specialist, then report back.\n"
            "- Confirm before anything irreversible."
        ),
    },
    "voice": "ash",
    "model_provider": "openai",
    "model_name": "gpt-4o-mini",
    "task_type": "normal",
    "tool_ids": ["list_agents", "create_agent", "send_message_to_agent", "run_debate", "coding_session", "web_search", "http_request"],
    "memory_policy": {"strategy": "external"},
    "guardrails": {"max_iterations": 12, "max_cost_per_run_usd": "0.50"},
}

# A standing "company" of specialists Jarvis can delegate to — planning,
# engineering, marketing, design, ops — so a high-level goal fans out to a team.
COMPANY = [
    {
        "name": "Athena the Strategist",
        "role": "Head of strategy — turns a goal into a concrete plan with milestones",
        "system_prompt": "Given a goal, produce a crisp plan: objective, the key steps, who/what each needs, and risks. Be decisive.",
        "soul_md": "You are Athena. You see the whole board and cut to the critical path. You plan in outcomes, not activities.",
        "persona": {"traits": ["strategic", "decisive"], "tone": "executive"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Devin the Engineer",
        "role": "Builds technical solutions and writes code",
        "system_prompt": "Given a technical task, design the approach and write clean, correct code with a short explanation.",
        "soul_md": "You are Devin. Pragmatic and precise. You ship working code and call out trade-offs honestly.",
        "persona": {"traits": ["pragmatic", "rigorous"], "tone": "technical"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "coding",
        "tool_ids": ["python_exec", "coding_session"],
    },
    {
        "name": "Mara the Marketer",
        "role": "Marketing expert — positioning, messaging, and go-to-market",
        "system_prompt": "Given a product or goal, craft sharp positioning: audience, value prop, key messages, and a launch angle.",
        "soul_md": "You are Mara. You make people care. You lead with the benefit and kill jargon on sight.",
        "persona": {"traits": ["persuasive", "creative"], "tone": "punchy"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Pixel the Designer",
        "role": "Product designer — UX flows and interface concepts",
        "system_prompt": "Given a feature or product, propose the UX: the core flow, key screens, and the one thing that must feel great.",
        "soul_md": "You are Pixel. You design for clarity first and delight second. You sweat the empty states.",
        "persona": {"traits": ["user-centric", "tasteful"], "tone": "thoughtful"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Otto the Ops Lead",
        "role": "Operations & finance — budgets, timelines, and execution logistics",
        "system_prompt": "Given a plan, lay out the operational reality: rough budget, timeline, dependencies, and what could slip.",
        "soul_md": "You are Otto. You turn plans into schedules and money. You are allergic to hand-waving.",
        "persona": {"traits": ["organised", "grounded"], "tone": "matter-of-fact"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Pip the PM",
        "role": "Product manager — turns ambiguity into a crisp PRD with prioritised scope",
        "system_prompt": "Given a product idea or problem, produce a one-page PRD: the user, the job, success metric, MVP scope, and what's deliberately out.",
        "soul_md": "You are Pip. You write the doc nobody else wants to write. You make trade-offs explicit and protect the team from scope creep.",
        "persona": {"traits": ["decisive", "user-obsessed"], "tone": "structured"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Iris the Voice",
        "role": "User researcher — runs interviews and translates them into insight",
        "system_prompt": "Given a research goal, design 5 user-interview questions, then synthesise raw quotes into 3 themes with verbatim evidence.",
        "soul_md": "You are Iris. You believe the truth is in the user's own words. You ask the obvious question nobody else dared to ask.",
        "persona": {"traits": ["empathetic", "incisive"], "tone": "warm but probing"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
    {
        "name": "Sage the Data Scientist",
        "role": "Numbers, patterns, A/B tests — turns metrics into a decision",
        "system_prompt": "Given metrics or a question, run the relevant analysis (or stub it), report the effect size + confidence, and recommend the action.",
        "soul_md": "You are Sage. You don't fall in love with a chart. You report what the data actually says, including 'we don't know yet'.",
        "persona": {"traits": ["rigorous", "skeptical"], "tone": "calm"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
        "tool_ids": ["python_exec"],
    },
    {
        "name": "Lex the Counsel",
        "role": "Legal & risk — spots compliance, privacy, and contract pitfalls",
        "system_prompt": "Given a proposal, flag the legal/privacy/risk concerns plainly and suggest mitigations. Never offer formal legal advice; cite when uncertain.",
        "soul_md": "You are Lex. Pragmatic, not pedantic. You raise the issue once, clearly, then help us ship within the lines.",
        "persona": {"traits": ["measured", "thorough"], "tone": "professional"},
        "model_provider": "openai", "model_name": "gpt-4o-mini", "task_type": "normal",
    },
]

# Slack-style team channels seeded so /team has prebuilt collaborative spaces.
# (channel_name → list of agent names that belong; missing names are tolerated.)
TEAM_CHANNELS: list[dict] = [
    {"name": "growth", "members": ["Mara the Marketer", "Pixel the Designer", "Sage the Data Scientist", "Iris the Voice"]},
    {"name": "product", "members": ["Pip the PM", "Pixel the Designer", "Devin the Engineer", "Sage the Data Scientist"]},
    {"name": "research", "members": ["Remy the Researcher", "Ana the Analyst", "Iris the Voice", "Sage the Data Scientist"]},
]

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

# ── Tool-showcase templates ───────────────────────────────────────────────────
# Each one surfaces a distinct capability on the run timeline so the demo can
# point at it: built-in tool, MCP tool, and the human-approval gate.

CITED_RESEARCH_NAME = "Cited Research (demo)"
# Explicit web_search TOOL node before any agent runs — its result lands in
# state.artifacts.search_results and feeds the research agent. The tool call
# renders as its own step in the timeline so the "real tools" claim is visible.

MCP_PAGE_NAME = "Page Summariser · MCP (demo)"
# Two MCP Playwright nodes (navigate + snapshot) → agent summary. Shows the
# MCP integration end-to-end without any backend code change to add browser
# capability — it's all provisioned through the MCP client.

PRD_APPROVAL_NAME = "PRD with Approval (demo)"
# Pip drafts a PRD → human approval gate → Mara positions → Brie briefs.
# The pause-resume flow is what makes human-in-the-loop tangible.


async def main() -> None:
    configure_logging()
    async with SessionFactory() as s:
        agent_repo = AgentRepository(s)
        ids: dict[str, str] = {}
        for spec in [JARVIS] + COMPANY + AGENTS + LOOP_AGENTS:
            existing = await agent_repo.get_by_name(spec["name"])
            if existing:
                ids[spec["name"]] = str(existing.id)
                log.info("seed.agent.exists", name=spec["name"])
                continue
            defaults = dict(
                model_provider="anthropic", temperature=0.7, max_tokens=1024,
                # Long-term memory by default so agents remember their work across
                # tasks and self-improve from evaluations.
                memory_policy={"strategy": "external"},
                guardrails={"max_iterations": 6, "max_cost_per_run_usd": "0.50"}, harness={},
            )
            merged = {**defaults, **spec}
            # Every agent can collaborate: discover teammates + delegate/escalate.
            merged["tool_ids"] = sorted({*(merged.get("tool_ids") or []), "list_agents", "send_message_to_agent"})
            agent = await agent_repo.create(**merged)
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

        # ── Cited Research: TOOL node feeds agent chain ──────────────────────
        if not any(w.name == CITED_RESEARCH_NAME for w in await wf_repo.list()):
            graph = {
                "version": "1.0",
                "name": CITED_RESEARCH_NAME,
                "description": "web_search → Remy cites the sources → Ana analyses → Brie writes the brief.",
                "entry_node": "search",
                "variables": {"topic": {"type": "string", "required": True}},
                "nodes": [
                    {"id": "search", "type": "tool", "tool": "web_search",
                     "input_mapping": {"query": "$.variables.topic"},
                     "output_key": "sources"},
                    {"id": "cite", "type": "agent", "agent_id": ids["Remy the Researcher"],
                     "input_mapping": {"sources": "$.artifacts.sources", "topic": "$.variables.topic"},
                     "output_key": "research"},
                    {"id": "analyse", "type": "agent", "agent_id": ids["Ana the Analyst"],
                     "input_mapping": {"notes": "$.artifacts.research"},
                     "output_key": "analysis"},
                    {"id": "brief", "type": "agent", "agent_id": ids["Brie the Briefer"],
                     "input_mapping": {"analysis": "$.artifacts.analysis"},
                     "output_key": "brief"},
                ],
                "edges": [
                    {"id": "e1", "from": "search", "to": "cite"},
                    {"id": "e2", "from": "cite", "to": "analyse"},
                    {"id": "e3", "from": "analyse", "to": "brief"},
                ],
            }
            await wf_repo.create(name=CITED_RESEARCH_NAME, graph=graph, description=graph["description"])
            log.info("seed.workflow.created", name=CITED_RESEARCH_NAME)
        else:
            log.info("seed.workflow.exists", name=CITED_RESEARCH_NAME)

        # ── Page Summariser: MCP browser tools → agent ───────────────────────
        if not any(w.name == MCP_PAGE_NAME for w in await wf_repo.list()):
            graph = {
                "version": "1.0",
                "name": MCP_PAGE_NAME,
                "description": "mcp_playwright navigates + snapshots a URL → Brie writes a one-paragraph summary.",
                "entry_node": "open",
                "variables": {"url": {"type": "string", "required": True}},
                "nodes": [
                    {"id": "open", "type": "tool", "tool": "mcp__playwright__browser_navigate",
                     "input_mapping": {"url": "$.variables.url"},
                     "output_key": "navigated"},
                    {"id": "snap", "type": "tool", "tool": "mcp__playwright__browser_snapshot",
                     "output_key": "page_snapshot"},
                    {"id": "summarise", "type": "agent", "agent_id": ids["Brie the Briefer"],
                     "input_mapping": {"page": "$.artifacts.page_snapshot", "url": "$.variables.url"},
                     "output_key": "summary"},
                ],
                "edges": [
                    {"id": "e1", "from": "open", "to": "snap"},
                    {"id": "e2", "from": "snap", "to": "summarise"},
                ],
            }
            await wf_repo.create(name=MCP_PAGE_NAME, graph=graph, description=graph["description"])
            log.info("seed.workflow.created", name=MCP_PAGE_NAME)
        else:
            log.info("seed.workflow.exists", name=MCP_PAGE_NAME)

        # ── PRD with Approval: human gate splits the run in two halves ──────
        if not any(w.name == PRD_APPROVAL_NAME for w in await wf_repo.list()) and "Pip the PM" in ids:
            graph = {
                "version": "1.0",
                "name": PRD_APPROVAL_NAME,
                "description": "Pip drafts a PRD → you approve → Mara positions → Brie briefs.",
                "entry_node": "prd",
                "variables": {"idea": {"type": "string", "required": True}},
                "nodes": [
                    {"id": "prd", "type": "agent", "agent_id": ids["Pip the PM"],
                     "input_mapping": {"idea": "$.variables.idea"},
                     "output_key": "draft_prd"},
                    {"id": "approve", "type": "human",
                     "label": "Approve the PRD before positioning + briefing?"},
                    {"id": "position", "type": "agent", "agent_id": ids["Mara the Marketer"],
                     "input_mapping": {"prd": "$.artifacts.draft_prd"},
                     "output_key": "positioning"},
                    {"id": "brief", "type": "agent", "agent_id": ids["Brie the Briefer"],
                     "input_mapping": {"prd": "$.artifacts.draft_prd", "positioning": "$.artifacts.positioning"},
                     "output_key": "brief"},
                ],
                "edges": [
                    {"id": "e1", "from": "prd", "to": "approve"},
                    {"id": "e2", "from": "approve", "to": "position"},
                    {"id": "e3", "from": "position", "to": "brief"},
                ],
            }
            await wf_repo.create(name=PRD_APPROVAL_NAME, graph=graph, description=graph["description"])
            log.info("seed.workflow.created", name=PRD_APPROVAL_NAME)
        else:
            log.info("seed.workflow.exists", name=PRD_APPROVAL_NAME)

        # Seeded team channels — Slack-style spaces with prebuilt rosters so
        # /team isn't an empty page. Idempotent on (name).
        existing_channels = {c.name: c for c in (await s.execute(select(TeamChannel))).scalars().all()}
        for chan in TEAM_CHANNELS:
            if chan["name"] in existing_channels:
                # Backfill agent_ids if seed adds new members later.
                want = [ids[n] for n in chan["members"] if n in ids]
                if set(existing_channels[chan["name"]].agent_ids or []) != set(want):
                    existing_channels[chan["name"]].agent_ids = want
                    log.info("seed.channel.updated", name=chan["name"], n=len(want))
                else:
                    log.info("seed.channel.exists", name=chan["name"])
                continue
            members = [ids[n] for n in chan["members"] if n in ids]
            s.add(TeamChannel(name=chan["name"], agent_ids=members))
            log.info("seed.channel.created", name=chan["name"], n=len(members))

        await s.commit()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())
