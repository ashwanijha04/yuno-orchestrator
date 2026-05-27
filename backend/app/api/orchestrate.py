"""Orchestrate — the one-shot 'give a task, watch agents collaborate' entrypoint.

Builds a workflow on the fly from a task + selected agents and enqueues it:
  - pipeline: chain the selected agents, piping each output to the next
  - auto:     a Coordinator agent (with send_message_to_agent) plans + delegates
              to the selected agents at runtime, then synthesizes

Returns the run_id; the UI streams the live timeline on the same screen.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RunOut
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import get_session
from app.runtime import queue

router = APIRouter(prefix="/orchestrate", tags=["orchestrate"])

COORDINATOR_NAME = "Orchestrator"


class OrchestrateRequest(BaseModel):
    task: str
    agent_ids: list[uuid.UUID] = Field(default_factory=list)
    mode: Literal["pipeline", "auto"] = "pipeline"
    max_cost_usd: str | None = None


async def _get_or_create_coordinator(session: AsyncSession):
    repo = AgentRepository(session)
    existing = await repo.get_by_name(COORDINATOR_NAME)
    if existing:
        return existing
    return await repo.create(
        name=COORDINATOR_NAME,
        role="Coordinates a team of agents to complete a task",
        system_prompt=(
            "You are an orchestrator. Break the task into subtasks and delegate each "
            "to the most suitable available agent using the send_message_to_agent tool "
            "(recipient = the agent's exact name). Then synthesize their replies into a "
            "final answer."
        ),
        model_provider="openai",
        model_name="gpt-4o-mini",
        task_type="normal",
        tool_ids=["send_message_to_agent"],
        memory_policy={"strategy": "buffer"},
        guardrails={"max_iterations": 8},
        harness={},
    )


@router.post("", response_model=RunOut, status_code=201)
async def orchestrate(body: OrchestrateRequest, session: AsyncSession = Depends(get_session)):
    if not body.task.strip():
        raise HTTPException(422, "task is required")

    agent_repo = AgentRepository(session)
    agents = [a for a in [await agent_repo.get(aid) for aid in body.agent_ids] if a]
    if body.mode == "pipeline" and not agents:
        raise HTTPException(422, "pipeline mode needs at least one agent")

    if body.mode == "auto":
        coordinator = await _get_or_create_coordinator(session)
        # If the user didn't pick agents, the orchestrator chooses from the whole
        # roster itself (goal -> auto-plan -> delegate).
        if not agents:
            agents = [a for a in await agent_repo.list() if a.name != COORDINATOR_NAME]
        roster = "\n".join(f"- {a.name}: {a.role}" for a in agents) or "(no other agents available)"
        graph = {
            "version": "1.0", "name": "Orchestration (auto)", "entry_node": "coordinator",
            "variables": {"task": {"type": "string"}},
            "nodes": [{"id": "coordinator", "type": "agent", "agent_id": str(coordinator.id),
                       "input_mapping": {"task": "$.variables.task", "available_agents": "$.variables.roster"},
                       "output_key": "result"}],
            "edges": [],
        }
        variables = {"task": body.task, "roster": roster}
    else:  # pipeline
        nodes, edges = [], []
        for i, a in enumerate(agents):
            nid = f"step{i}"
            mapping = {"input": "$.variables.task"} if i == 0 else {"input": f"$.artifacts.out{i - 1}"}
            nodes.append({"id": nid, "type": "agent", "agent_id": str(a.id),
                          "input_mapping": mapping, "output_key": f"out{i}", "label": a.name})
            if i > 0:
                edges.append({"id": f"e{i}", "from": f"step{i - 1}", "to": nid})
        graph = {
            "version": "1.0", "name": "Orchestration (pipeline)", "entry_node": "step0",
            "variables": {"task": {"type": "string"}}, "nodes": nodes, "edges": edges,
        }
        variables = {"task": body.task}

    wf = await WorkflowRepository(session).create(
        name=f"Orchestration · {uuid.uuid4().hex[:8]}", graph=graph, description=body.task[:200]
    )
    trigger_payload: dict = {"task": body.task}
    if body.max_cost_usd:
        trigger_payload["max_cost_usd"] = body.max_cost_usd
    run = await RunRepository(session).create(
        workflow_id=wf.id, workflow_version=1, trigger_type="manual",
        trigger_payload=trigger_payload, initial_state={"variables": variables},
    )
    await session.commit()
    await queue.ensure_group()
    await queue.enqueue_run(run.id)
    return run
