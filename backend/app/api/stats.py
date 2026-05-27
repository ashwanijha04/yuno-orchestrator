"""Dashboard stats — aggregate counts, cost, and status breakdown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, Channel, Run, Workflow
from app.db.session import get_session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def stats(session: AsyncSession = Depends(get_session)):
    async def count(model) -> int:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()

    midnight = datetime.now(UTC) - timedelta(hours=24)

    runs_total = await count(Run)
    runs_today = (await session.execute(
        select(func.count()).select_from(Run).where(Run.started_at >= midnight)
    )).scalar_one()

    status_rows = (await session.execute(select(Run.status, func.count()).group_by(Run.status))).all()
    by_status = {s: c for s, c in status_rows}

    cost = (await session.execute(select(func.coalesce(func.sum(Run.total_cost_usd), 0)))).scalar_one()
    tin = (await session.execute(select(func.coalesce(func.sum(Run.total_tokens_in), 0)))).scalar_one()
    tout = (await session.execute(select(func.coalesce(func.sum(Run.total_tokens_out), 0)))).scalar_one()

    return {
        "agents": await count(Agent),
        "workflows": await count(Workflow),
        "channels": await count(Channel),
        "runs_total": runs_total,
        "runs_today": runs_today,
        "running": by_status.get("running", 0) + by_status.get("pending", 0),
        "completed": by_status.get("completed", 0),
        "failed": by_status.get("failed", 0),
        "total_cost_usd": str(cost),
        "total_tokens": int(tin) + int(tout),
    }
