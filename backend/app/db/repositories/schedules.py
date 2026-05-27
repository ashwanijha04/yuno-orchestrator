"""Schedule persistence + cron computation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Schedule


def next_after(cron_expression: str, base: datetime | None = None) -> datetime:
    base = base or datetime.now(UTC)
    return croniter(cron_expression, base).get_next(datetime)


class ScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, workflow_id: uuid.UUID, cron_expression: str, payload: dict | None = None
    ) -> Schedule:
        sched = Schedule(
            workflow_id=workflow_id,
            cron_expression=cron_expression,
            enabled=True,
            next_run_at=next_after(cron_expression),
            payload=payload,
        )
        self.session.add(sched)
        await self.session.flush()
        return sched

    async def list(self) -> Sequence[Schedule]:
        result = await self.session.execute(select(Schedule).order_by(Schedule.next_run_at))
        return result.scalars().all()

    async def due(self, now: datetime | None = None) -> Sequence[Schedule]:
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
        )
        return result.scalars().all()

    async def mark_fired(self, schedule: Schedule) -> None:
        schedule.last_run_at = datetime.now(UTC)
        schedule.next_run_at = next_after(schedule.cron_expression)
        await self.session.flush()

    async def set_enabled(self, schedule_id: uuid.UUID, enabled: bool) -> Schedule | None:
        sched = await self.session.get(Schedule, schedule_id)
        if sched is None:
            return None
        sched.enabled = enabled
        await self.session.flush()
        return sched
