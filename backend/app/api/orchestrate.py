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
    mode: Literal["pipeline", "auto"] = "auto"  # agentic by default
    max_cost_usd: str | None = None


SYSTEM_PROMPT = (
    "You are an orchestrator that completes a task by coordinating a team of agents.\n\n"
    "Your toolkit:\n"
    "- list_agents — see which agents already exist (reuse one before creating a duplicate).\n"
    "- create_agent — spin up a NEW specialist when none fits; give it a clear name, a one-line role, "
    "and a focused system_prompt. It returns the exact name to delegate to.\n"
    "- send_message_to_agent — delegate a concrete subtask to an agent by its EXACT name; it runs that "
    "agent and returns its reply for you to use.\n\n"
    "Process:\n"
    "1. Break the task into a few concrete subtasks.\n"
    "2. For each subtask, reuse a fitting existing agent, or create_agent a new specialist for it.\n"
    "3. Delegate the subtask with send_message_to_agent and use the reply. Never delegate the same "
    "subtask twice.\n"
    "4. When you have everything you need, STOP calling tools and write the final synthesized answer "
    "for the user.\n\n"
    "Be decisive: prefer creating one well-scoped specialist over many tiny ones."
)
GUARDRAILS = {"max_iterations": 12, "max_cost_per_run_usd": "0.50"}
COORDINATOR_TOOLS = ["list_agents", "create_agent", "send_message_to_agent"]


async def _get_or_create_coordinator(session: AsyncSession):
    repo = AgentRepository(session)
    existing = await repo.get_by_name(COORDINATOR_NAME)
    if existing:
        # Keep the existing coordinator's prompt/tools/guardrails current.
        return await repo.update(
            existing.id, system_prompt=SYSTEM_PROMPT, guardrails=GUARDRAILS, tool_ids=COORDINATOR_TOOLS
        )
    return await repo.create(
        name=COORDINATOR_NAME,
        role="Coordinates a team of agents to complete a task",
        system_prompt=SYSTEM_PROMPT,
        model_provider="openai",
        model_name="gpt-4o-mini",
        task_type="normal",
        tool_ids=COORDINATOR_TOOLS,
        memory_policy={"strategy": "buffer"},
        guardrails=GUARDRAILS,
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
