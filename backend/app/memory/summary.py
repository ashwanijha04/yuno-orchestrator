"""SummaryMemory — keep the last K verbatim; older context is meant to be folded
into a rolling LLM summary. The trigger/threshold is implemented here; the actual
summarization LLM call is a documented extension (kept out of the hot path for
the demo). Until then it behaves as a bounded buffer with a summary marker.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.memory.base import MemoryContext
from app.memory.buffer import BufferMemory

_ROLES = ("user", "assistant", "agent")


class SummaryMemory:
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages

    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        recent = await BufferMemory(self.max_messages).load(agent_id, ctx, session)
        if not ctx.run_id:
            return recent
        total = (
            await session.execute(
                select(func.count(Message.id)).where(Message.run_id == ctx.run_id, Message.role.in_(_ROLES))
            )
        ).scalar_one()
        # Once history exceeds the window, prepend a summary placeholder so the
        # agent knows context was elided (production replaces this with an LLM
        # summary of the older messages).
        if total > self.max_messages:
            elided = total - len(recent)
            return [{"role": "system", "content": f"[summary] {elided} earlier messages elided."}] + recent
        return recent
