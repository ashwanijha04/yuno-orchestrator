"""Agent CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AgentCreate, AgentOut, AgentUpdate
from app.db.repositories import AgentRepository
from app.db.session import get_session

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
async def list_agents(session: AsyncSession = Depends(get_session)):
    return list(await AgentRepository(session).list())


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentCreate, session: AsyncSession = Depends(get_session)):
    repo = AgentRepository(session)
    if await repo.get_by_name(body.name):
        raise HTTPException(409, f"agent named {body.name!r} already exists")
    agent = await repo.create(**body.model_dump())
    await session.commit()
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    agent = await AgentRepository(session).get(agent_id)
    if agent is None:
        raise HTTPException(404, "agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID, body: AgentUpdate, session: AsyncSession = Depends(get_session)
):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    agent = await AgentRepository(session).update(agent_id, **fields)
    if agent is None:
        raise HTTPException(404, "agent not found")
    await session.commit()
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if not await AgentRepository(session).delete(agent_id):
        raise HTTPException(404, "agent not found")
    await session.commit()
