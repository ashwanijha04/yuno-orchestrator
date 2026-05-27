"""Run endpoints: list, detail (steps + messages), and a quick-run trigger that
wraps a single agent in a synthetic one-node workflow and enqueues it."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ChildRun,
    MessageOut,
    QuickRunRequest,
    RunDetail,
    RunOut,
    RunWorkflowRequest,
    StepOut,
)
from app.db.models import Agent, Workflow
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import get_session
from app.runtime import queue
from sqlalchemy import select

router = APIRouter(prefix="/runs", tags=["runs"])


def _task_of(run) -> str | None:
    tp = run.trigger_payload or {}
    vars_ = (run.initial_state or {}).get("variables", {})
    for src in (tp, vars_):
        for k in ("task", "topic", "text", "input", "message"):
            if src.get(k):
                return str(src[k])
    return None


@router.get("", response_model=list[RunOut])
async def list_runs(session: AsyncSession = Depends(get_session)):
    runs = await RunRepository(session).list()
    wf_ids = {r.workflow_id for r in runs}
    names: dict = {}
    if wf_ids:
        rows = (await session.execute(select(Workflow.id, Workflow.name).where(Workflow.id.in_(wf_ids)))).all()
        names = {wid: name for wid, name in rows}
    out = []
    for r in runs:
        item = RunOut.model_validate(r)
        item.workflow_name = names.get(r.workflow_id)
        item.task = _task_of(r)
        out.append(item)
    return out


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = RunRepository(session)
    run = await repo.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    steps = await repo.steps_for_run(run_id)
    messages = await repo.messages_for_run(run_id)

    # Resolve agent names for the steps.
    agent_ids = {s.agent_id for s in steps if s.agent_id}
    agent_names: dict = {}
    if agent_ids:
        rows = (await session.execute(select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids)))).all()
        agent_names = {aid: name for aid, name in rows}
    # The agent's output = its last non-empty assistant message in the step
    # (for an orchestrator, earlier turns are tool calls; the last is the synthesis).
    step_output: dict = {}
    for m in messages:
        if m.step_id and m.role == "assistant" and m.content.strip():
            step_output[m.step_id] = m.content  # last with content wins

    wf = await session.get(Workflow, run.workflow_id)
    step_outs = []
    for s in steps:
        so = StepOut.model_validate(s)
        so.agent_name = agent_names.get(s.agent_id)
        so.output = step_output.get(s.id)
        step_outs.append(so)

    # Delegated sub-tasks (runs spawned via send_message_to_agent).
    children = await repo.children_of(run_id)
    child_outs: list[ChildRun] = []
    child_agent_names: list[str] = []
    for c in children:
        csteps = await repo.steps_for_run(c.id)
        c_aids = {s.agent_id for s in csteps if s.agent_id}
        cnames = {}
        if c_aids:
            rows = (await session.execute(select(Agent.id, Agent.name).where(Agent.id.in_(c_aids)))).all()
            cnames = {aid: name for aid, name in rows}
        cmsgs = await repo.messages_for_run(c.id)
        coutput = next((m.content for m in reversed(cmsgs) if m.role == "assistant"), None)
        aname = next(iter(cnames.values()), None) or (c.trigger_payload or {}).get("recipient")
        if aname:
            child_agent_names.append(aname)
        child_outs.append(ChildRun(
            id=c.id, agent_name=aname, task=(c.trigger_payload or {}).get("message"),
            status=c.status, output=coutput, total_cost_usd=c.total_cost_usd,
        ))

    base = RunOut.model_validate(run)
    base.workflow_name = wf.name if wf else None
    base.task = _task_of(run)
    base.agent_names = [agent_names[a] for a in agent_ids if a in agent_names] + child_agent_names
    return RunDetail(
        **base.model_dump(), steps=step_outs,
        messages=[MessageOut.model_validate(m) for m in messages], children=child_outs,
    )


@router.post("/workflow/{workflow_id}", response_model=RunOut, status_code=201)
async def run_workflow(
    workflow_id: uuid.UUID, body: RunWorkflowRequest, session: AsyncSession = Depends(get_session)
):
    """Trigger a (multi-agent) workflow at its current version and enqueue it."""
    wf = await WorkflowRepository(session).get(workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")

    trigger_payload: dict = dict(body.variables)
    if body.max_cost_usd is not None:
        trigger_payload["max_cost_usd"] = str(body.max_cost_usd)

    run = await RunRepository(session).create(
        workflow_id=workflow_id,
        workflow_version=wf.current_version,
        trigger_type="manual",
        trigger_payload=trigger_payload,
        initial_state={"variables": body.variables},
    )
    await session.commit()
    await queue.ensure_group()
    await queue.enqueue_run(run.id)
    return run


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
