"""ChannelScopedMemory — messages scoped to a channel user across separate runs.

This is how a Telegram bot remembers a person between conversations: gather the
recent messages from all runs that originated from the same channel_external_id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Run
from app.memory.base import MemoryContext

_ROLES = ("user", "assistant", "agent")


class ChannelScopedMemory:
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages

    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        if not ctx.channel_external_id:
            # No channel context (e.g. manual run) — fall back to this run only.
            from app.memory.buffer import BufferMemory

            return await BufferMemory(self.max_messages).load(agent_id, ctx, session)

        # Runs triggered by this channel user.
        run_ids = (
            await session.execute(
                select(Run.id).where(
                    Run.trigger_type == "channel",
                    Run.trigger_payload["external_id"].astext == ctx.channel_external_id,
                )
            )
        ).scalars().all()
        if not run_ids:
            return []
        rows = (
            await session.execute(
                select(Message)
                .where(Message.run_id.in_(run_ids), Message.role.in_(_ROLES))
                .order_by(Message.ts.desc())
                .limit(self.max_messages)
            )
        ).scalars().all()
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]
