"""BufferMemory — the last N messages within the current run."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.memory.base import MemoryContext

_ROLES = ("user", "assistant", "agent")


class BufferMemory:
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages

    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        if not ctx.run_id:
            return []
        rows = (
            await session.execute(
                select(Message)
                .where(Message.run_id == ctx.run_id, Message.role.in_(_ROLES))
                .order_by(Message.ts.desc())
                .limit(self.max_messages)
            )
        ).scalars().all()
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]
