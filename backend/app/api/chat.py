"""1:1 chat with an agent. Each turn runs the agent inline (so the reply is
immediate) with conversation-scoped memory keyed by conversation_id. Turns are
real runs, so they show up in the timeline and cost ledger too."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Run
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import SessionFactory, get_session
from app.runtime.engine import RunEngine

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    agent_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    message: str


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    run_id: uuid.UUID


async def _chat_workflow(s: AsyncSession, agent) -> uuid.UUID:
    """One reusable single-node workflow per agent for chat turns."""
    name = f"__chat__{agent.id}"
    for wf in await WorkflowRepository(s).list():
        if wf.name == name:
            return wf.id
    graph = {
        "version": "1.0", "name": name, "entry_node": "main",
        "variables": {"input": {"type": "string"}},
        "nodes": [{"id": "main", "type": "agent", "agent_id": str(agent.id),
                   "input_mapping": {"input": "$.variables.input"}, "output_key": "reply"}],
        "edges": [],
    }
    wf = await WorkflowRepository(s).create(name=name, graph=graph)
    return wf.id


@router.post("", response_model=ChatResponse)
async def send(body: ChatRequest, session: AsyncSession = Depends(get_session)):
    agent = await AgentRepository(session).get(body.agent_id)
    if agent is None:
        raise HTTPException(404, "agent not found")
    conversation_id = body.conversation_id or uuid.uuid4()

    workflow_id = await _chat_workflow(session, agent)
    run = await RunRepository(session).create(
        workflow_id=workflow_id, workflow_version=1, trigger_type="chat",
        trigger_payload={"conversation_id": str(conversation_id), "agent_id": str(agent.id)},
        initial_state={"variables": {"input": body.message}},
    )
    # Persist the user's turn so it shows in the thread and in conversation memory.
    await RunRepository(session).add_message(run.id, role="user", content=body.message, agent_id=agent.id)
    await session.commit()
    run_id = run.id

    # Run inline so the reply is immediate (provider=None -> ModelRouter / live).
    await RunEngine(session_factory=SessionFactory).run(run_id)

    async with SessionFactory() as s:
        msgs = await RunRepository(s).messages_for_run(run_id)
    reply = next((m.content for m in reversed(msgs) if m.role == "assistant"), "(no reply)")
    return ChatResponse(conversation_id=conversation_id, reply=reply, run_id=run_id)


@router.get("/{conversation_id}", response_model=list[ChatTurn])
async def history(conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    run_ids = (
        await session.execute(
            select(Run.id).where(Run.trigger_payload["conversation_id"].astext == str(conversation_id))
        )
    ).scalars().all()
    if not run_ids:
        return []
    rows = (
        await session.execute(
            select(Message)
            .where(Message.run_id.in_(run_ids), Message.role.in_(("user", "assistant")))
            .order_by(Message.ts)
        )
    ).scalars().all()
    return [ChatTurn(role=m.role, content=m.content) for m in rows]
