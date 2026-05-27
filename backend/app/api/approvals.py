"""Human-in-the-loop approvals: list what's waiting, and approve/reject to
resume (or cancel) a paused workflow run."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ApprovalRepository, RunRepository
from app.db.session import get_session
from app.runtime import queue

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    node_id: str
    summary: str
    status: str
    note: str | None = None

    class Config:
        from_attributes = True


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


@router.get("", response_model=list[ApprovalOut])
async def list_pending(session: AsyncSession = Depends(get_session)):
    return await ApprovalRepository(session).pending()


@router.post("/{approval_id}", response_model=ApprovalOut)
async def decide(
    approval_id: uuid.UUID, body: DecisionRequest, session: AsyncSession = Depends(get_session)
):
    repo = ApprovalRepository(session)
    approval = await repo.get(approval_id)
    if approval is None:
        raise HTTPException(404, "approval not found")
    if approval.status != "pending":
        raise HTTPException(409, f"approval already {approval.status}")

    if body.decision == "reject":
        await repo.decide(approval_id, "rejected", note=body.note)
        await RunRepository(session).set_status(approval.run_id, "cancelled", error="Rejected at approval")
        await session.commit()
        return approval

    # Approve → mark approved and re-enqueue the run so the engine resumes it.
    await repo.decide(approval_id, "approved", note=body.note)
    await RunRepository(session).set_status(approval.run_id, "pending")
    await session.commit()
    await queue.ensure_group()
    await queue.enqueue_run(approval.run_id)
    return approval
