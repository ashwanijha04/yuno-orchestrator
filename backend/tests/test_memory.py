"""Memory strategies: buffer eviction, summary elision marker, external degrade."""

from __future__ import annotations

import asyncio
import uuid

import pytest_asyncio

from app.db.repositories import RunRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.memory import MemoryContext, get_memory_strategy


@pytest_asyncio.fixture
async def clean(engine):
    yield


async def _run_with_messages(n: int) -> uuid.UUID:
    async with SessionFactory() as s:
        wf = await WorkflowRepository(s).create(name=f"M-{uuid.uuid4().hex[:6]}", graph={"entry_node": "a", "nodes": [], "edges": []})
        run = await RunRepository(s).create(workflow_id=wf.id, workflow_version=1, trigger_type="manual")
        await s.commit()
        run_id = run.id
    # Commit each message separately (distinct now()) so ordering is deterministic.
    for i in range(n):
        async with SessionFactory() as s:
            await RunRepository(s).add_message(run_id, role="user" if i % 2 == 0 else "assistant", content=f"msg{i}")
            await s.commit()
        await asyncio.sleep(0.002)
    return run_id


async def test_buffer_returns_last_n_in_order(clean):
    run_id = await _run_with_messages(6)
    strat = get_memory_strategy({"strategy": "buffer", "max_messages": 3})
    async with SessionFactory() as s:
        out = await strat.load(uuid.uuid4(), MemoryContext(run_id=str(run_id)), s)
    assert [m["content"] for m in out] == ["msg3", "msg4", "msg5"]


async def test_summary_prepends_elision_marker(clean):
    run_id = await _run_with_messages(6)
    strat = get_memory_strategy({"strategy": "summary", "max_messages": 2})
    async with SessionFactory() as s:
        out = await strat.load(uuid.uuid4(), MemoryContext(run_id=str(run_id)), s)
    assert out[0]["role"] == "system" and "elided" in out[0]["content"]
    assert [m["content"] for m in out[1:]] == ["msg4", "msg5"]


async def test_external_degrades_to_buffer_when_extremis_absent(clean):
    # No EXTREMIS_URL/STORE in the test env -> recall returns None -> buffer.
    run_id = await _run_with_messages(2)
    strat = get_memory_strategy({"strategy": "external", "max_messages": 5})
    async with SessionFactory() as s:
        out = await strat.load(uuid.uuid4(), MemoryContext(run_id=str(run_id)), s)
    assert [m["content"] for m in out] == ["msg0", "msg1"]
