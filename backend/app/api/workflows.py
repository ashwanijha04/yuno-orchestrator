"""Workflow listing + detail (graph). Authoring (visual builder / versioned
edits) lands in Phase 8; for now workflows arrive via the seed and templates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ValidateRequest,
    ValidateResponse,
    ValidationIssueOut,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowOut,
    WorkflowSaveVersion,
)
from app.db.models import Agent
from app.db.repositories import WorkflowRepository
from app.db.session import get_session
from app.runtime.validation import validate_graph

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def _known_agent_ids(session: AsyncSession) -> set[str]:
    rows = (await session.execute(select(Agent.id))).scalars().all()
    return {str(r) for r in rows}


# Workflows created automatically for chat / quick-run / orchestrate / inter-agent
# messages are plumbing, not user artifacts — hide them from the Workflows tab.
_SYNTHETIC_PREFIXES = ("Quick ·", "msg->", "chat:", "__chat__", "Orchestration", "debate->", "channel:")


def _is_synthetic(name: str) -> bool:
    return any(name.startswith(p) for p in _SYNTHETIC_PREFIXES)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(session: AsyncSession = Depends(get_session)):
    repo = WorkflowRepository(session)
    workflows = [w for w in await repo.list() if not _is_synthetic(w.name)]
    # Latest run status per workflow, in one query.
    from app.db.models import Run

    last: dict = {}
    if workflows:
        rows = (
            await session.execute(
                select(Run.workflow_id, Run.status, Run.started_at)
                .where(Run.workflow_id.in_([w.id for w in workflows]))
                .order_by(Run.started_at.desc())
            )
        ).all()
        for wid, status, started in rows:
            last.setdefault(wid, (status, started))

    out: list[WorkflowOut] = []
    for w in workflows:
        item = WorkflowOut.model_validate(w)
        graph = await repo.get_current_graph(w.id) or {}
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        item.node_count = len(nodes)
        item.agent_count = sum(1 for n in nodes if n.get("type", "agent") == "agent")
        badges: list[str] = []
        tools = [n for n in nodes if n.get("type") == "tool"]
        if any(str(n.get("tool", "")).startswith("mcp__") for n in tools):
            badges.append("mcp")
        if any(not str(n.get("tool", "")).startswith("mcp__") for n in tools):
            badges.append("tools")
        if any(n.get("type") == "human" for n in nodes):
            badges.append("human")
        if any(e.get("condition") for e in edges):
            badges.append("branch")
        if any(n.get("on_error") for n in nodes):
            badges.append("error")
        item.badges = badges
        item.is_template = bool(w.template_id) or w.name.endswith("(demo)")
        if w.id in last:
            item.last_run_status, item.last_run_at = last[w.id]
        out.append(item)
    return out


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if not await WorkflowRepository(session).delete(workflow_id):
        raise HTTPException(404, "workflow not found")
    await session.commit()


@router.post("/{workflow_id}/duplicate", response_model=WorkflowDetail, status_code=201)
async def duplicate_workflow(workflow_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = WorkflowRepository(session)
    wf = await repo.get(workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    graph = await repo.get_current_graph(workflow_id) or {}
    # Names are unique — suffix to avoid collisions on repeated duplicates.
    copy = await repo.create(name=f"{wf.name} (copy {uuid.uuid4().hex[:4]})", graph=graph, description=wf.description)
    await session.commit()
    return WorkflowDetail(**WorkflowOut.model_validate(copy).model_dump(), graph=graph)


@router.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest, session: AsyncSession = Depends(get_session)):
    issues = validate_graph(body.graph, known_agent_ids=await _known_agent_ids(session))
    return ValidateResponse(
        valid=len(issues) == 0,
        issues=[ValidationIssueOut(code=i.code, message=i.message, node_id=i.node_id, edge_id=i.edge_id) for i in issues],
    )


@router.post("", response_model=WorkflowDetail, status_code=201)
async def create_workflow(body: WorkflowCreate, session: AsyncSession = Depends(get_session)):
    # Validate before persisting so the builder can't save a broken graph.
    issues = validate_graph(body.graph, known_agent_ids=await _known_agent_ids(session))
    blocking = [i for i in issues if i.code != "unreachable"]  # warn-only: unreachable
    if blocking:
        raise HTTPException(422, detail={"issues": [i.__dict__ for i in blocking]})
    wf = await WorkflowRepository(session).create(name=body.name, graph=body.graph, description=body.description)
    await session.commit()
    return WorkflowDetail(**WorkflowOut.model_validate(wf).model_dump(), graph=body.graph)


@router.post("/{workflow_id}/versions", response_model=WorkflowDetail)
async def save_version(workflow_id: uuid.UUID, body: WorkflowSaveVersion, session: AsyncSession = Depends(get_session)):
    repo = WorkflowRepository(session)
    if await repo.get(workflow_id) is None:
        raise HTTPException(404, "workflow not found")
    issues = validate_graph(body.graph, known_agent_ids=await _known_agent_ids(session))
    blocking = [i for i in issues if i.code != "unreachable"]
    if blocking:
        raise HTTPException(422, detail={"issues": [i.__dict__ for i in blocking]})
    await repo.new_version(workflow_id, body.graph)
    wf = await repo.get(workflow_id)
    await session.commit()
    return WorkflowDetail(**WorkflowOut.model_validate(wf).model_dump(), graph=body.graph)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(workflow_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = WorkflowRepository(session)
    wf = await repo.get(workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    graph = await repo.get_current_graph(workflow_id)
    return WorkflowDetail(**WorkflowOut.model_validate(wf).model_dump(), graph=graph or {})
