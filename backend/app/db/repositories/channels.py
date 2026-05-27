"""Channel + binding persistence, including webhook-routing resolution."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, ChannelBinding


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, type: str, name: str, config: dict | None = None) -> Channel:
        channel = Channel(type=type, name=name, config=config or {})
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def get(self, channel_id: uuid.UUID) -> Channel | None:
        return await self.session.get(Channel, channel_id)

    async def list(self) -> Sequence[Channel]:
        result = await self.session.execute(select(Channel).order_by(Channel.created_at))
        return result.scalars().all()

    async def add_binding(
        self, channel_id: uuid.UUID, external_id: str,
        agent_id: uuid.UUID | None = None, workflow_id: uuid.UUID | None = None,
        config: dict | None = None,
    ) -> ChannelBinding:
        binding = ChannelBinding(
            channel_id=channel_id, external_id=external_id, agent_id=agent_id,
            workflow_id=workflow_id, config=config or {},
        )
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def bindings_for_channel(self, channel_id: uuid.UUID) -> Sequence[ChannelBinding]:
        result = await self.session.execute(
            select(ChannelBinding).where(ChannelBinding.channel_id == channel_id)
        )
        return result.scalars().all()

    async def resolve_binding(
        self, channel_id: uuid.UUID, external_id: str
    ) -> ChannelBinding | None:
        """Find the binding for an inbound message (webhook routing entrypoint)."""
        result = await self.session.execute(
            select(ChannelBinding).where(
                ChannelBinding.channel_id == channel_id,
                ChannelBinding.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()
