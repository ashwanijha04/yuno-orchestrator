"""Scheduler: due detection + next_run_at advancement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from app.db.repositories import ScheduleRepository, WorkflowRepository
from app.db.repositories.schedules import next_after
from app.db.session import SessionFactory


@pytest_asyncio.fixture
async def clean(engine):
    yield


def test_next_after_is_in_future():
    nxt = next_after("*/5 * * * *")
    assert nxt > datetime.now(UTC)


async def test_due_detection_and_advance(clean):
    async with SessionFactory() as s:
        wf = await WorkflowRepository(s).create(name=f"S-{uuid.uuid4().hex[:6]}", graph={"entry_node": "a", "nodes": [], "edges": []})
        repo = ScheduleRepository(s)
        sched = await repo.create(workflow_id=wf.id, cron_expression="*/5 * * * *", payload={"topic": "x"})
        # Force it past-due.
        sched.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
        sched_id = sched.id

    async with SessionFactory() as s:
        repo = ScheduleRepository(s)
        due = await repo.due()
        assert any(d.id == sched_id for d in due)
        target = next(d for d in due if d.id == sched_id)
        await repo.mark_fired(target)
        await s.commit()

    async with SessionFactory() as s:
        repo = ScheduleRepository(s)
        # After firing, next_run_at is in the future -> no longer due.
        assert not any(d.id == sched_id for d in await repo.due())
