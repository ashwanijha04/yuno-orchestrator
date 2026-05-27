"""Channel + binding management. Connecting an agent to a channel is a binding
(agent <-> channel <-> optional workflow), not a field on the agent — one agent
can be reachable on several channels. Live Telegram delivery lands in Phase 6."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import BindingCreate, BindingOut, ChannelCreate, ChannelOut
from app.db.repositories import ChannelRepository
from app.db.session import get_session

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
async def list_channels(session: AsyncSession = Depends(get_session)):
    return list(await ChannelRepository(session).list())


@router.post("", response_model=ChannelOut, status_code=201)
async def create_channel(body: ChannelCreate, session: AsyncSession = Depends(get_session)):
    channel = await ChannelRepository(session).create(
        type=body.type, name=body.name, config=body.config
    )
    await session.commit()
    return channel


@router.get("/{channel_id}/bindings", response_model=list[BindingOut])
async def list_bindings(channel_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return list(await ChannelRepository(session).bindings_for_channel(channel_id))


@router.post("/{channel_id}/bindings", response_model=BindingOut, status_code=201)
async def create_binding(
    channel_id: uuid.UUID, body: BindingCreate, session: AsyncSession = Depends(get_session)
):
    repo = ChannelRepository(session)
    if await repo.get(channel_id) is None:
        raise HTTPException(404, "channel not found")
    binding = await repo.add_binding(
        channel_id=channel_id,
        external_id=body.external_id,
        agent_id=body.agent_id,
        workflow_id=body.workflow_id,
        config=body.config,
    )
    await session.commit()
    return binding
