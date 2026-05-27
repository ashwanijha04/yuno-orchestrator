"""send_message_to_agent — synchronous inter-agent delegation.

Records the handoff on the caller's run (visible "who talks to whom"), creates a
*linked child run* for the recipient, runs it inline, and RETURNS the recipient's
reply so the caller (e.g. an orchestrator) can use it and decide what to do next.
Returning the reply is what stops an orchestrator from blindly re-delegating.

Recipients themselves don't get the delegation tool, so there's no recursion.
"""

from __future__ import annotations

import uuid

from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
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
            if ctx.run_id is not None:
                await runs.add_message(
                    ctx.run_id, role="agent", content=content,
                    agent_id=ctx.agent_id, recipient_agent_id=target.id,
                )
            graph = {
                "version": "1.0", "name": f"msg->{target.name}", "entry_node": "main",
                "variables": {"message": {"type": "string"}},
                "nodes": [{"id": "main", "type": "agent", "agent_id": str(target.id),
                           "input_mapping": {"message": "$.variables.message"}, "output_key": "reply"}],
                "edges": [],
            }
            wf = await WorkflowRepository(s).create(
                name=f"msg->{target.name}·{uuid.uuid4().hex[:8]}", graph=graph
            )
            child = await runs.create(
                workflow_id=wf.id, workflow_version=1, trigger_type="agent",
                trigger_payload={
                    "from_agent": str(ctx.agent_id), "message": content,
                    "recipient": target.name,
                    "parent_run_id": str(ctx.run_id) if ctx.run_id else None,
                },
                initial_state={"variables": {"message": content, "input": content}},
            )
            await s.commit()
            child_id, recipient_name = child.id, target.name

        # Run the recipient inline so we can return its reply to the caller.
        # Lazy import avoids the engine<->tools import cycle.
        from app.runtime.engine import RunEngine

        await RunEngine(session_factory=ctx.session_factory).run(child_id)

        async with ctx.session_factory() as s:
            msgs = await RunRepository(s).messages_for_run(child_id)
        reply = next((m.content for m in reversed(msgs) if m.role == "assistant"), "(no reply)")
        return {"status": "completed", "recipient": recipient_name, "reply": reply, "run_id": str(child_id)}
