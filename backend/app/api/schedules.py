"""Schedule CRUD — cron-triggered workflow runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import ScheduleRepository, WorkflowRepository
from app.db.repositories.schedules import next_after
from app.db.session import get_session

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    workflow_id: uuid.UUID
    cron_expression: str
    payload: dict = Field(default_factory=dict)


class ScheduleOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    cron_expression: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(session: AsyncSession = Depends(get_session)):
    return list(await ScheduleRepository(session).list())


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(body: ScheduleCreate, session: AsyncSession = Depends(get_session)):
    if await WorkflowRepository(session).get(body.workflow_id) is None:
        raise HTTPException(404, "workflow not found")
    try:
        next_after(body.cron_expression)  # validate the cron expression
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, f"invalid cron expression: {exc}") from exc
    sched = await ScheduleRepository(session).create(
        workflow_id=body.workflow_id, cron_expression=body.cron_expression, payload=body.payload
    )
    await session.commit()
    return sched


@router.post("/{schedule_id}/enabled", response_model=ScheduleOut)
async def set_enabled(schedule_id: uuid.UUID, enabled: bool, session: AsyncSession = Depends(get_session)):
    sched = await ScheduleRepository(session).set_enabled(schedule_id, enabled)
    if sched is None:
        raise HTTPException(404, "schedule not found")
    await session.commit()
    return sched
