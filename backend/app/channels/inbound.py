"""Inbound message handling: resolve a binding and enqueue a channel-triggered
run. Shared by the webhook endpoint and the polling loop.

Binding resolution: exact (channel_id, external_id) first, then a channel-wide
default binding with external_id='*' (so a bot can serve any chat).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.channels.base import InboundMessage
from app.db.models import ChannelBinding, OutboundMessage
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.logging import get_logger
from app.runtime import queue

log = get_logger("channels.inbound")


async def _resolve_binding(s, channel_id: uuid.UUID, external_id: str) -> ChannelBinding | None:
    for ext in (external_id, "*"):
        b = (
            await s.execute(
                select(ChannelBinding).where(
                    ChannelBinding.channel_id == channel_id, ChannelBinding.external_id == ext
                )
            )
        ).scalars().first()
        if b:
            return b
    return None


async def handle_inbound(inbound: InboundMessage, session_factory: async_sessionmaker) -> uuid.UUID | None:
    channel_id = uuid.UUID(inbound.channel_id)
    async with session_factory() as s:
        binding = await _resolve_binding(s, channel_id, inbound.external_id)
        if binding is None:
            log.warning("inbound.no_binding", channel_id=str(channel_id), external_id=inbound.external_id)
            return None

        # Greet on /start with a canned welcome instead of spinning up the model.
        if inbound.content.strip().lower() in ("/start", "/help"):
            agent = await AgentRepository(s).get(binding.agent_id) if binding.agent_id else None
            name = agent.name if agent else "your assistant"
            welcome = (
                f"👋 I'm {name}, your AI chief of staff. Ask me anything — I can plan work, "
                "build a team of agents, run debates, and I remember our conversations. "
                "What can I do for you?"
            )
            s.add(OutboundMessage(channel_id=channel_id, external_id=inbound.external_id, content=welcome, status="pending"))
            await s.commit()
            return None

        workflows = WorkflowRepository(s)
        workflow_id: uuid.UUID | None = binding.workflow_id

        if workflow_id is None and binding.agent_id is not None:
            agent = await AgentRepository(s).get(binding.agent_id)
            if agent and agent.default_workflow_id:
                workflow_id = agent.default_workflow_id
            elif agent:
                # Synthetic single-node workflow so a bare agent is conversational.
                graph = {
                    "version": "1.0", "name": f"chat:{agent.name}", "entry_node": "main",
                    "variables": {"input": {"type": "string"}},
                    "nodes": [{"id": "main", "type": "agent", "agent_id": str(agent.id),
                               "input_mapping": {"input": "$.variables.input"}, "output_key": "reply"}],
                    "edges": [],
                }
                wf = await workflows.create(name=f"chat:{agent.name}·{uuid.uuid4().hex[:8]}", graph=graph)
                workflow_id = wf.id

        if workflow_id is None:
            log.warning("inbound.no_workflow", channel_id=str(channel_id))
            return None

        wf = await workflows.get(workflow_id)
        run = await RunRepository(s).create(
            workflow_id=workflow_id,
            workflow_version=wf.current_version,
            trigger_type="channel",
            trigger_payload={
                "channel_id": str(channel_id), "external_id": inbound.external_id, "text": inbound.content,
                # Stable per-chat id so the engine loads prior turns -> the bot
                # holds a coherent multi-turn conversation (and blends long-term
                # memory for external-memory agents like Jarvis).
                "conversation_id": f"tg:{channel_id}:{inbound.external_id}",
            },
            initial_state={"variables": {"input": inbound.content, "message": inbound.content, "topic": inbound.content}},
        )
        await s.commit()
        run_id = run.id

    await queue.ensure_group()
    await queue.enqueue_run(run_id)
    log.info("inbound.run_enqueued", run_id=str(run_id), external_id=inbound.external_id)
    return run_id
