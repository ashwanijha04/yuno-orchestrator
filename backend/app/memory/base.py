"""Memory subsystem. Memory is *queried, not pushed*: the prepare step asks a
strategy for the messages to inject. Strategies are selected per-agent via
`agents.memory_policy.strategy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class MemoryContext:
    run_id: str | None
    channel_external_id: str | None = None
    max_messages: int = 20
    query: str | None = None  # the current input, used as the long-term recall cue


@runtime_checkable
class MemoryStrategy(Protocol):
    async def load(self, agent_id, ctx: MemoryContext, session: AsyncSession) -> list[dict]:
        """Return [{role, content}] to inject ahead of the current input."""
        ...


def get_memory_strategy(policy: dict | None):
    """Factory: map an agent's memory_policy to a strategy instance."""
    from app.memory.buffer import BufferMemory
    from app.memory.channel_scoped import ChannelScopedMemory
    from app.memory.external import ExternalMemoryStrategy
    from app.memory.summary import SummaryMemory

    policy = policy or {}
    strategy = policy.get("strategy", "buffer")
    n = int(policy.get("max_messages", 20))
    if strategy == "summary":
        return SummaryMemory(max_messages=n)
    if strategy == "channel_scoped":
        return ChannelScopedMemory(max_messages=n)
    if strategy == "external":
        return ExternalMemoryStrategy(max_messages=n)
    return BufferMemory(max_messages=n)
