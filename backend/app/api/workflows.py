"""Workflow listing + detail (graph). Authoring (visual builder / versioned
edits) lands in Phase 8; for now workflows arrive via the seed and templates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import WorkflowDetail, WorkflowOut
from app.db.repositories import WorkflowRepository
from app.db.session import get_session

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(session: AsyncSession = Depends(get_session)):
    return list(await WorkflowRepository(session).list())


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(workflow_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = WorkflowRepository(session)
    wf = await repo.get(workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    graph = await repo.get_current_graph(workflow_id)
    return WorkflowDetail(**WorkflowOut.model_validate(wf).model_dump(), graph=graph or {})
