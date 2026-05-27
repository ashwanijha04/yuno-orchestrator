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
_SYNTHETIC_PREFIXES = ("Quick ·", "msg->", "chat:", "__chat__", "Orchestration")


def _is_synthetic(name: str) -> bool:
    return any(name.startswith(p) for p in _SYNTHETIC_PREFIXES)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(session: AsyncSession = Depends(get_session)):
    return [w for w in await WorkflowRepository(session).list() if not _is_synthetic(w.name)]


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
