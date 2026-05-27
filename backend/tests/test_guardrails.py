"""Guardrails: the per-agent cost circuit-breaker trips in a real run."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest_asyncio

from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.runtime.engine import RunEngine


@pytest_asyncio.fixture
async def clean(engine):
    yield


async def test_cost_cap_guardrail_trips_in_run(clean):
    async with SessionFactory() as s:
        agent = await AgentRepository(s).create(
            name="Spendy", role="r", system_prompt="Answer at length.",
            model_provider="stub", model_name="claude-opus-4-7",  # priced model
            guardrails={"max_cost_per_run_usd": "0.0000001"},  # effectively zero
        )
        graph = {"name": "G", "entry_node": "a", "variables": {},
                 "nodes": [{"id": "a", "type": "agent", "agent_id": str(agent.id), "output_key": "out"}], "edges": []}
        wf = await WorkflowRepository(s).create(name=f"G-{uuid.uuid4().hex[:6]}", graph=graph)
        run = await RunRepository(s).create(workflow_id=wf.id, workflow_version=1, trigger_type="manual", initial_state={"variables": {"input": "hello"}})
        await s.commit()
        run_id = run.id

    # Provider would raise if called; being blocked pre-call proves the breaker.
    engine = RunEngine(session_factory=SessionFactory, provider=StubProvider(Script([]), strict=True), executor=HarnessExecutor(backoff_base_s=0))
    await engine.run(run_id)

    async with SessionFactory() as s:
        repo = RunRepository(s)
        msgs = await repo.messages_for_run(run_id)
        run = await repo.get(run_id)
    assert any(m.content.startswith("[blocked") for m in msgs)
    assert run.total_cost_usd == Decimal("0")
