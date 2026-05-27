"""Run / step / message persistence + cost roll-up.

Costs are denormalized up the hierarchy at write time: a message's cost adds to
its step and its run, so dashboard queries stay trivial.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Run, Step


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, workflow_id: uuid.UUID, workflow_version: int, trigger_type: str,
        trigger_payload: dict | None = None, initial_state: dict | None = None,
    ) -> Run:
        run = Run(
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            initial_state=initial_state,
            status="pending",
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get(self, run_id: uuid.UUID) -> Run | None:
        return await self.session.get(Run, run_id)

    async def list(self, limit: int = 50) -> Sequence[Run]:
        result = await self.session.execute(
            select(Run).order_by(Run.started_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def set_status(
        self, run_id: uuid.UUID, status: str, error: str | None = None,
        final_state: dict | None = None,
    ) -> Run | None:
        run = await self.get(run_id)
        if run is None:
            return None
        run.status = status
        if error is not None:
            run.error = error
        if final_state is not None:
            run.final_state = final_state
        if status in ("completed", "failed", "cancelled"):
            run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def add_step(self, run_id: uuid.UUID, node_id: str, **fields) -> Step:
        step = Step(run_id=run_id, node_id=node_id, **fields)
        self.session.add(step)
        await self.session.flush()
        return step

    async def complete_step(
        self, step_id: uuid.UUID, status: str, error: str | None = None
    ) -> Step | None:
        step = await self.session.get(Step, step_id)
        if step is None:
            return None
        step.status = status
        step.error = error
        step.completed_at = datetime.now(UTC)
        await self.session.flush()
        return step

    async def add_message(
        self, run_id: uuid.UUID, role: str, content: str,
        step_id: uuid.UUID | None = None, cost_usd: Decimal = Decimal("0"),
        tokens_in: int = 0, tokens_out: int = 0, **fields,
    ) -> Message:
        """Persist a message and roll its cost/tokens up to the step and run."""
        message = Message(
            run_id=run_id, step_id=step_id, role=role, content=content,
            cost_usd=cost_usd, tokens_in=tokens_in, tokens_out=tokens_out, **fields,
        )
        self.session.add(message)

        run = await self.get(run_id)
        if run is not None:
            run.total_cost_usd = run.total_cost_usd + cost_usd
            run.total_tokens_in += tokens_in
            run.total_tokens_out += tokens_out
        if step_id is not None:
            step = await self.session.get(Step, step_id)
            if step is not None:
                step.cost_usd = step.cost_usd + cost_usd
                step.tokens_in += tokens_in
                step.tokens_out += tokens_out
        await self.session.flush()
        return message

    async def messages_for_run(self, run_id: uuid.UUID) -> Sequence[Message]:
        result = await self.session.execute(
            select(Message).where(Message.run_id == run_id).order_by(Message.ts)
        )
        return result.scalars().all()

    async def steps_for_run(self, run_id: uuid.UUID) -> Sequence[Step]:
        result = await self.session.execute(
            select(Step).where(Step.run_id == run_id).order_by(Step.started_at)
        )
        return result.scalars().all()

    async def children_of(self, run_id: uuid.UUID) -> Sequence[Run]:
        """Runs spawned by this run via send_message_to_agent (delegated sub-tasks)."""
        result = await self.session.execute(
            select(Run)
            .where(Run.trigger_payload["parent_run_id"].astext == str(run_id))
            .order_by(Run.started_at)
        )
        return result.scalars().all()
