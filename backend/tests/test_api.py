"""API tests: agent CRUD, and the full local run loop (quick-run -> queue ->
engine with stub provider -> run completes with persisted steps/messages)."""

from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.main import app
from app.runtime import queue
from app.runtime.engine import RunEngine


@pytest_asyncio.fixture
async def client(engine):  # engine fixture resets + binds the DB
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


AGENT_BODY = {
    "name": "Researcher",
    "role": "Web research specialist",
    "system_prompt": "Research thoroughly.",
    "model_provider": "stub",
    "model_name": "claude-sonnet-4-5",
}


async def test_agent_crud(client):
    # create
    r = await client.post("/agents", json=AGENT_BODY)
    assert r.status_code == 201, r.text
    agent = r.json()
    assert agent["name"] == "Researcher"

    # duplicate name -> 409
    assert (await client.post("/agents", json=AGENT_BODY)).status_code == 409

    # list / get
    assert len(((await client.get("/agents")).json())) == 1
    assert (await client.get(f"/agents/{agent['id']}")).json()["role"] == "Web research specialist"

    # update / delete
    r = await client.patch(f"/agents/{agent['id']}", json={"role": "Lead researcher"})
    assert r.json()["role"] == "Lead researcher"
    assert (await client.delete(f"/agents/{agent['id']}")).status_code == 204
    assert (await client.get(f"/agents/{agent['id']}")).status_code == 404


async def test_quick_run_executes_end_to_end(client):
    r = await client.post("/agents", json=AGENT_BODY)
    agent_id = r.json()["id"]

    # Reset the queue so we only see this run.
    from app.redis_client import get_redis

    await get_redis().delete(queue.STREAM)

    r = await client.post(f"/runs/agent/{agent_id}", json={"input": "What is the capital of France?"})
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "pending"
    run_id = run["id"]

    # Simulate the worker: claim the enqueued run and execute it with a stub.
    batch = await queue.claim_batch("test-worker", count=10, block_ms=1000)
    assert run_id in [rid for _e, rid in batch]
    engine = RunEngine(
        session_factory=SessionFactory,
        provider=StubProvider(Script([]), strict=False),
        executor=HarnessExecutor(backoff_base_s=0),
    )
    status = await engine.run(uuid.UUID(run_id))
    assert status == "completed"

    # Run detail reflects the executed step + message.
    detail = (await client.get(f"/runs/{run_id}")).json()
    assert detail["status"] == "completed"
    assert [s["node_id"] for s in detail["steps"]] == ["main"]
    assert detail["messages"][0]["content"].startswith("[stub] acknowledged")
    assert detail["total_tokens_out"] > 0
