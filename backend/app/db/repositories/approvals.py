"""Approval records for the human-in-the-loop `human` workflow node."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Approval


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, run_id: uuid.UUID, node_id: str, summary: str, state: dict | None = None
    ) -> Approval:
        approval = Approval(run_id=run_id, node_id=node_id, summary=summary, state=state)
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get(self, approval_id: uuid.UUID) -> Approval | None:
        return await self.session.get(Approval, approval_id)

    async def pending(self) -> Sequence[Approval]:
        result = await self.session.execute(
            select(Approval).where(Approval.status == "pending").order_by(Approval.created_at.desc())
        )
        return result.scalars().all()

    async def for_run(self, run_id: uuid.UUID) -> Sequence[Approval]:
        result = await self.session.execute(
            select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at)
        )
        return result.scalars().all()

    async def latest_approved(self, run_id: uuid.UUID) -> Approval | None:
        result = await self.session.execute(
            select(Approval)
            .where(Approval.run_id == run_id, Approval.status == "approved")
            .order_by(Approval.decided_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def decide(self, approval_id: uuid.UUID, status: str, note: str | None = None) -> Approval | None:
        approval = await self.get(approval_id)
        if approval is None:
            return None
        approval.status = status
        approval.note = note
        approval.decided_at = datetime.now(UTC)
        await self.session.flush()
        return approval
