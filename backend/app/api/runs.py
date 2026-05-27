"""Run endpoints: list, detail (steps + messages), and a quick-run trigger that
wraps a single agent in a synthetic one-node workflow and enqueues it."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MessageOut, QuickRunRequest, RunDetail, RunOut, StepOut
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import get_session
from app.runtime import queue

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
async def list_runs(session: AsyncSession = Depends(get_session)):
    return list(await RunRepository(session).list())


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = RunRepository(session)
    run = await repo.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    steps = await repo.steps_for_run(run_id)
    messages = await repo.messages_for_run(run_id)
    return RunDetail(
        **RunOut.model_validate(run).model_dump(),
        steps=[StepOut.model_validate(s) for s in steps],
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.post("/agent/{agent_id}", response_model=RunOut, status_code=201)
async def quick_run(
    agent_id: uuid.UUID, body: QuickRunRequest, session: AsyncSession = Depends(get_session)
):
    """Run one agent as a synthetic single-node workflow, then enqueue it."""
    agent = await AgentRepository(session).get(agent_id)
    if agent is None:
        raise HTTPException(404, "agent not found")

    graph = {
        "version": "1.0",
        "name": f"Quick · {agent.name}",
        "entry_node": "main",
        "variables": {"input": {"type": "string", "required": True}},
        "nodes": [
            {"id": "main", "type": "agent", "agent_id": str(agent_id), "output_key": "output"}
        ],
        "edges": [],
    }
    wf_repo = WorkflowRepository(session)
    workflow = await wf_repo.create(name=f"Quick · {agent.name} · {uuid.uuid4().hex[:8]}", graph=graph)

    trigger_payload: dict = {"input": body.input}
    if body.max_cost_usd is not None:
        trigger_payload["max_cost_usd"] = str(body.max_cost_usd)

    run = await RunRepository(session).create(
        workflow_id=workflow.id,
        workflow_version=1,
        trigger_type="manual",
        trigger_payload=trigger_payload,
        initial_state={"variables": {"input": body.input}},
    )
    await session.commit()

    await queue.ensure_group()
    await queue.enqueue_run(run.id)
    return run
