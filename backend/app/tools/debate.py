"""run_debate — a structured multi-round debate among several agents.

Each round, every participant argues the topic while seeing the transcript so
far, so they genuinely respond to one another. Each turn is a linked child run
(like a delegation), so it shows up in the live conversation view and lights up
the constellation. The full transcript is returned so the caller (Jarvis) can
weigh the arguments and make the final call.

Participants are existing agents that don't hold the orchestration tools, so a
debate can't recurse into more debates.
"""

from __future__ import annotations

import uuid

from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.tools.base import ToolContext


async def _run_turn(ctx: ToolContext, target, full_prompt: str, label: str) -> str:
    """Run one participant's turn as a linked child run; return what they said.
    The child receives `full_prompt` (topic + transcript); the timeline shows the
    short `label` so the conversation stays readable."""
    async with ctx.session_factory() as s:
        runs = RunRepository(s)
        if ctx.run_id is not None:
            await runs.add_message(
                ctx.run_id, role="agent", content=label,
                agent_id=ctx.agent_id, recipient_agent_id=target.id,
            )
        graph = {
            "version": "1.0", "name": f"debate->{target.name}", "entry_node": "main",
            "variables": {"message": {"type": "string"}},
            "nodes": [{"id": "main", "type": "agent", "agent_id": str(target.id),
                       "input_mapping": {"message": "$.variables.message"}, "output_key": "reply"}],
            "edges": [],
        }
        wf = await WorkflowRepository(s).create(name=f"debate->{target.name}·{uuid.uuid4().hex[:8]}", graph=graph)
        child = await runs.create(
            workflow_id=wf.id, workflow_version=1, trigger_type="agent",
            trigger_payload={
                "from_agent": str(ctx.agent_id), "message": label, "recipient": target.name,
                "parent_run_id": str(ctx.run_id) if ctx.run_id else None,
            },
            initial_state={"variables": {"message": full_prompt, "input": full_prompt}},
        )
        await s.commit()
        child_id = child.id

    from app.runtime.engine import RunEngine  # lazy: avoid engine<->tools cycle

    await RunEngine(session_factory=ctx.session_factory).run(child_id)
    async with ctx.session_factory() as s:
        msgs = await RunRepository(s).messages_for_run(child_id)
    return next((m.content for m in reversed(msgs) if m.role == "assistant"), "(no response)")


class RunDebateTool:
    name = "run_debate"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        topic = str(input.get("topic", "")).strip()
        names = input.get("participants") or []
        rounds = max(1, min(int(input.get("rounds", 2) or 2), 3))
        if not topic or not isinstance(names, list) or len(names) < 2:
            return {"error": "topic and a participants list of at least 2 agent names are required"}

        async with ctx.session_factory() as s:
            repo = AgentRepository(s)
            agents = [a for a in [await repo.get_by_name(str(n)) for n in names[:4]] if a]
        if len(agents) < 2:
            return {"error": "could not resolve at least 2 participants by name (use exact agent names)"}

        transcript: list[str] = []
        for r in range(rounds):
            for a in agents:
                so_far = "\n\n".join(transcript) if transcript else "(you speak first — open the debate)"
                prompt = (
                    f"You are taking part in a structured debate as {a.name}.\n"
                    f"TOPIC: {topic}\n\n"
                    f"ARGUMENTS SO FAR:\n{so_far}\n\n"
                    f"This is round {r + 1} of {rounds}. State your position in 2–4 sentences, "
                    f"engaging directly with points others have made. Be persuasive but intellectually honest."
                )
                said = await _run_turn(ctx, a, prompt, label=f"Debate · round {r + 1} · {topic[:48]}")
                transcript.append(f"{a.name}: {said}")

        return {
            "status": "completed", "topic": topic, "rounds": rounds,
            "participants": [a.name for a in agents],
            "transcript": transcript,
            "note": "Weigh these arguments and give the user your final decision/recommendation.",
        }
