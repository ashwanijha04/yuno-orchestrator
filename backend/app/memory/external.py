"""ExternalMemoryStrategy — episodic + procedural recall from extremis (the
identity/memory layer the soul anchors to). The continuous-learning loop
(New Task -> recall, Observe -> report_outcome, Encode Skill -> consolidate)
hangs off this strategy.

Degrades gracefully: if extremis isn't installed/reachable, it falls back to
BufferMemory and logs a warning, so the stack still runs (and the offline demo
still works) without it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.memory.base import MemoryContext
from app.memory.buffer import BufferMemory

log = get_logger("memory.external")


class ExternalMemoryStrategy:
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self._fallback = BufferMemory(max_messages)

    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        recalled = await self._recall(agent_id, ctx)
        if recalled is None:
            return await self._fallback.load(agent_id, ctx, session)
        # Blend recalled long-term memories ahead of the in-run buffer.
        buffer = await self._fallback.load(agent_id, ctx, session)
        return recalled + buffer

    async def _recall(self, agent_id, ctx: MemoryContext) -> list[dict] | None:
        if not settings.extremis_url and not settings.extremis_store:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{settings.extremis_url}/v1/memories/recall",
                    json={"namespace": str(agent_id), "limit": self.max_messages},
                )
                resp.raise_for_status()
                items = resp.json().get("memories", [])
            return [{"role": "system", "content": f"[memory] {m.get('content', '')}"} for m in items]
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            log.warning("extremis.recall_unavailable", detail=str(exc))
            return None
