"""Agent CRUD."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> Agent:
        agent = Agent(**fields)
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def get(self, agent_id: uuid.UUID) -> Agent | None:
        return await self.session.get(Agent, agent_id)

    async def get_by_name(self, name: str) -> Agent | None:
        result = await self.session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[Agent]:
        result = await self.session.execute(select(Agent).order_by(Agent.created_at))
        return result.scalars().all()

    async def update(self, agent_id: uuid.UUID, **fields) -> Agent | None:
        agent = await self.get(agent_id)
        if agent is None:
            return None
        for key, value in fields.items():
            setattr(agent, key, value)
        await self.session.flush()
        return agent

    async def delete(self, agent_id: uuid.UUID) -> bool:
        agent = await self.get(agent_id)
        if agent is None:
            return False
        await self.session.delete(agent)
        await self.session.flush()
        return True
