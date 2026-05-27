"""Tool protocol + execution context.

Tools get a constrained ToolContext (the single seam for capabilities) rather
than ambient authority: they can read state and reach the session factory for
the few writes they're allowed (e.g. enqueuing an inter-agent run), nothing more.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import async_sessionmaker


@dataclass
class ToolContext:
    run_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    session_factory: async_sessionmaker


@runtime_checkable
class Tool(Protocol):
    name: str

    async def execute(self, input: dict, ctx: ToolContext) -> dict[str, Any]: ...
