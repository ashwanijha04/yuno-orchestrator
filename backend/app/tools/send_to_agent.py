"""send_message_to_agent — async inter-agent messaging (run-per-message + inbox).

Writes a message row on the sender's run (so the handoff is visible on the
timeline / "who talks to whom"), then enqueues a *new run* for the recipient agent
as a synthetic single-node workflow. Not in-graph injection — every handoff is a
row and a run.
"""

from __future__ import annotations

import uuid

from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.runtime import queue
from app.tools.base import ToolContext


class SendToAgentTool:
    name = "send_message_to_agent"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        recipient = str(input.get("recipient", "")).strip()
        content = str(input.get("content", "")).strip()
        if not recipient or not content:
            return {"error": "recipient and content are required"}

        async with ctx.session_factory() as s:
            agents = AgentRepository(s)
            target = None
            try:
                target = await agents.get(uuid.UUID(recipient))
            except (ValueError, AttributeError):
                target = None
            if target is None:
                target = await agents.get_by_name(recipient)
            if target is None:
                return {"error": f"unknown recipient agent {recipient!r}"}

            runs = RunRepository(s)
            # Record the handoff on the sender's run for visibility.
            if ctx.run_id is not None:
                await runs.add_message(
                    ctx.run_id, role="agent", content=content,
                    agent_id=ctx.agent_id, recipient_agent_id=target.id,
                )

            graph = {
                "version": "1.0",
                "name": f"msg->{target.name}",
                "entry_node": "main",
                "variables": {"message": {"type": "string"}},
                "nodes": [{"id": "main", "type": "agent", "agent_id": str(target.id),
                           "input_mapping": {"message": "$.variables.message"}, "output_key": "reply"}],
                "edges": [],
            }
            wf = await WorkflowRepository(s).create(
                name=f"msg->{target.name}·{uuid.uuid4().hex[:8]}", graph=graph
            )
            new_run = await runs.create(
                workflow_id=wf.id, workflow_version=1, trigger_type="agent",
                trigger_payload={"from_agent": str(ctx.agent_id), "message": content},
                initial_state={"variables": {"message": content, "input": content}},
            )
            await s.commit()
            recipient_run_id = new_run.id
            recipient_name = target.name

        await queue.ensure_group()
        await queue.enqueue_run(recipient_run_id)
        return {"status": "sent", "recipient": recipient_name, "run_id": str(recipient_run_id)}
