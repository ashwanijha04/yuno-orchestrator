"""Run endpoints: list, detail (steps + messages), and a quick-run trigger that
wraps a single agent in a synthetic one-node workflow and enqueues it."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.api.schemas import (
    ChildRun,
    EvaluationOut,
    MessageOut,
    QuickRunRequest,
    RunDetail,
    RunOut,
    RunWorkflowRequest,
    StepOut,
)
from app.db.models import Agent, RunEvaluation, Step, Workflow
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import get_session
from app.runtime import queue
from sqlalchemy import select

router = APIRouter(prefix="/runs", tags=["runs"])


class FeedbackRequest(BaseModel):
    positive: bool
    note: str | None = None


async def _run_output(session: AsyncSession, run_id: uuid.UUID) -> str | None:
    msgs = await RunRepository(session).messages_for_run(run_id)
    return next((m.content for m in reversed(msgs) if m.role == "assistant" and m.content.strip()), None)


async def _external_memory_agents(session: AsyncSession, run_id: uuid.UUID) -> list[Agent]:
    rows = (
        await session.execute(select(Agent).join(Step, Step.agent_id == Agent.id).where(Step.run_id == run_id))
    ).scalars().unique().all()
    return [a for a in rows if (a.memory_policy or {}).get("strategy") == "external"]


async def _learn_from_eval(
    session: AsyncSession, run_id: uuid.UUID, task: str | None, output: str | None,
    positive: bool, note: str | None,
) -> None:
    """Distil a lesson into each external-memory agent's long-term memory."""
    agents = await _external_memory_agents(session, run_id)
    if not agents:
        return
    from app.memory.external import remember_lesson

    detail = (note or output or "").strip()[:400]
    if positive:
        lesson = f'For tasks like "{task}", a strong approach that scored well: {detail}'
    else:
        lesson = (
            f'For tasks like "{task}", the result fell short. To improve next time: '
            f'{detail or "be more accurate, relevant, and complete."}'
        )
    for a in agents:
        await remember_lesson(a.id, lesson)


def _task_of(run) -> str | None:
    tp = run.trigger_payload or {}
    vars_ = (run.initial_state or {}).get("variables", {})
    for src in (tp, vars_):
        for k in ("task", "topic", "text", "input", "message"):
            if src.get(k):
                return str(src[k])
    return None


@router.post("/clear")
async def clear_finished(session: AsyncSession = Depends(get_session)):
    deleted = await RunRepository(session).delete_finished()
    await session.commit()
    return {"deleted": deleted}


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if not await RunRepository(session).delete(run_id):
        raise HTTPException(404, "run not found")
    await session.commit()


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Request cancellation of an in-flight run. The engine checks the run's
    status cooperatively before each agent step and stops cleanly."""
    repo = RunRepository(session)
    run = await repo.get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status not in ("pending", "running"):
        raise HTTPException(409, f"run is {run.status}, cannot cancel")
    run = await repo.set_status(run_id, "cancelled", error="Cancelled by user")
    await session.commit()
    from app.observability.events import publish_event

    await publish_event(run_id, "run.cancelled", {})
    return run


@router.post("/{run_id}/evaluate", response_model=EvaluationOut)
async def evaluate_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Score a finished run with the LLM judge, then feed the verdict to the
    agents' long-term memory so they improve next time."""
    from app.eval import judge_run

    run = await RunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    task, output = _task_of(run), await _run_output(session, run_id)
    result = await judge_run(task or "", output or "")
    ev = RunEvaluation(
        run_id=run_id, source="judge", overall=result["overall"], scores=result["scores"],
        verdict=result["verdict"], rationale=result["rationale"], cost_usd=result["cost_usd"],
    )
    session.add(ev)
    await session.commit()
    if result["verdict"] is not None:
        await _learn_from_eval(
            session, run_id, task, output,
            positive=(result["verdict"] == "pass"), note=result["rationale"],
        )
    return ev


@router.post("/{run_id}/feedback", response_model=EvaluationOut)
async def feedback(run_id: uuid.UUID, body: FeedbackRequest, session: AsyncSession = Depends(get_session)):
    """Human 👍/👎 on a run. Outranks the judge and feeds the learn step."""
    run = await RunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ev = RunEvaluation(
        run_id=run_id, source="human", overall=(1.0 if body.positive else 0.0),
        scores={}, verdict=("pass" if body.positive else "fail"), rationale=body.note,
    )
    session.add(ev)
    await session.commit()
    await _learn_from_eval(
        session, run_id, _task_of(run), await _run_output(session, run_id),
        positive=body.positive, note=body.note,
    )
    return ev


@router.get("", response_model=list[RunOut])
async def list_runs(session: AsyncSession = Depends(get_session)):
    runs = await RunRepository(session).list()
    wf_ids = {r.workflow_id for r in runs}
    names: dict = {}
    if wf_ids:
        rows = (await session.execute(select(Workflow.id, Workflow.name).where(Workflow.id.in_(wf_ids)))).all()
        names = {wid: name for wid, name in rows}
    # Latest judge score per run, in one query (avoids N+1).
    quality: dict = {}
    if runs:
        ev_rows = (
            await session.execute(
                select(RunEvaluation.run_id, RunEvaluation.overall, RunEvaluation.created_at)
                .where(RunEvaluation.run_id.in_({r.id for r in runs}), RunEvaluation.source == "judge")
                .order_by(RunEvaluation.created_at.desc())
            )
        ).all()
        for rid, overall, _ in ev_rows:
            quality.setdefault(rid, overall)  # first seen = most recent
    out = []
    for r in runs:
        item = RunOut.model_validate(r)
        item.workflow_name = names.get(r.workflow_id)
        item.task = _task_of(r)
        item.quality = quality.get(r.id)
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

    # Evaluations (judge + human), newest first; quality = latest judge score.
    evals = (
        await session.execute(
            select(RunEvaluation).where(RunEvaluation.run_id == run_id).order_by(RunEvaluation.created_at.desc())
        )
    ).scalars().all()
    eval_outs = [EvaluationOut.model_validate(e) for e in evals]

    base = RunOut.model_validate(run)
    base.workflow_name = wf.name if wf else None
    base.task = _task_of(run)
    base.agent_names = [agent_names[a] for a in agent_ids if a in agent_names] + child_agent_names
    base.quality = next((e.overall for e in evals if e.source == "judge"), None)
    return RunDetail(
        **base.model_dump(), steps=step_outs,
        messages=[MessageOut.model_validate(m) for m in messages], children=child_outs,
        evaluations=eval_outs,
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
