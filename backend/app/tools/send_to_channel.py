"""send_to_channel — queue an outbound message to an external channel via the
transactional outbox. A dispatcher (Phase 6) delivers pending rows to Telegram etc.
"""

from __future__ import annotations

import uuid

from app.db.models import ChannelBinding, OutboundMessage
from sqlalchemy import select

from app.tools.base import ToolContext


class SendToChannelTool:
    name = "send_to_channel"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        content = str(input.get("content", "")).strip()
        if not content:
            return {"error": "content is required"}

        async with ctx.session_factory() as s:
            # Resolve a channel binding: explicit channel_id, else any binding for
            # this agent.
            binding: ChannelBinding | None = None
            channel_id = input.get("channel_id")
            if channel_id:
                binding = (
                    await s.execute(select(ChannelBinding).where(ChannelBinding.channel_id == uuid.UUID(str(channel_id))))
                ).scalars().first()
            elif ctx.agent_id is not None:
                binding = (
                    await s.execute(select(ChannelBinding).where(ChannelBinding.agent_id == ctx.agent_id))
                ).scalars().first()

            if binding is None:
                return {"status": "no_binding", "note": "agent is not bound to a channel; nothing sent"}

            s.add(OutboundMessage(
                channel_id=binding.channel_id, external_id=binding.external_id,
                content=content, status="pending",
            ))
            await s.commit()
        return {"status": "queued", "external_id": binding.external_id}
