"""Phase 5: tool execution (via the engine's tool runtime) + async inter-agent
messaging (send_message_to_agent enqueues a new run for the recipient)."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select

from app.db.models import Message, Run
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.runtime.engine import RunEngine


@pytest_asyncio.fixture
async def clean(engine):
    yield


async def _agent(name: str, tool_ids: list[str]) -> str:
    async with SessionFactory() as s:
        a = await AgentRepository(s).create(
            name=name, role="r", system_prompt="s", model_provider="stub", model_name="stub",
            tool_ids=tool_ids,
        )
        await s.commit()
        return str(a.id)


async def _single_node_run(agent_id: str, variables: dict) -> uuid.UUID:
    async with SessionFactory() as s:
        graph = {"name": "T", "entry_node": "main", "variables": {},
                 "nodes": [{"id": "main", "type": "agent", "agent_id": agent_id, "output_key": "out"}], "edges": []}
        wf = await WorkflowRepository(s).create(name=f"T-{uuid.uuid4().hex[:6]}", graph=graph)
        run = await RunRepository(s).create(workflow_id=wf.id, workflow_version=1, trigger_type="manual", initial_state={"variables": variables})
        await s.commit()
        return run.id


async def test_web_search_tool_executes(clean):
    agent_id = await _agent("Searcher", ["web_search"])
    run_id = await _single_node_run(agent_id, {"input": "find OpenAI news"})
    # Turn 1 calls the tool; turn 2 gives the final answer.
    script = Script([
        {"match": {"call_index": 0}, "response": {"content": "searching", "tool_calls": [{"name": "web_search", "input": {"query": "OpenAI"}}]}},
        {"match": {"call_index": 1}, "response": {"content": "Here is what I found."}},
    ])
    engine = RunEngine(session_factory=SessionFactory, provider=StubProvider(script), executor=HarnessExecutor(backoff_base_s=0))
    assert await engine.run(run_id) == "completed"

    async with SessionFactory() as s:
        msgs = await RunRepository(s).messages_for_run(run_id)
    roles = [m.role for m in msgs]
    assert "tool" in roles  # tool result persisted (visible on timeline)
    tool_msg = next(m for m in msgs if m.role == "tool")
    assert "stub" in tool_msg.content or "results" in tool_msg.content
    assert msgs[-1].content == "Here is what I found."


async def test_send_message_to_agent_enqueues_recipient_run(clean):
    sender = await _agent("Sender", ["send_message_to_agent"])
    async with SessionFactory() as s:
        recipient = await AgentRepository(s).create(name="Recipient", role="r", system_prompt="s", model_provider="stub", model_name="stub")
        await s.commit()
        recipient_id = recipient.id

    run_id = await _single_node_run(sender, {"input": "delegate"})
    script = Script([
        {"match": {"call_index": 0}, "response": {"content": "delegating", "tool_calls": [{"name": "send_message_to_agent", "input": {"recipient": "Recipient", "content": "please handle this"}}]}},
        {"match": {"call_index": 1}, "response": {"content": "done"}},
    ])
    engine = RunEngine(session_factory=SessionFactory, provider=StubProvider(script), executor=HarnessExecutor(backoff_base_s=0))
    assert await engine.run(run_id) == "completed"

    async with SessionFactory() as s:
        # A new run was created for the recipient (trigger_type='agent').
        agent_runs = (await s.execute(select(Run).where(Run.trigger_type == "agent"))).scalars().all()
        assert len(agent_runs) >= 1
        # The handoff message was recorded on the sender's run with a recipient.
        handoff = (await s.execute(
            select(Message).where(Message.run_id == run_id, Message.recipient_agent_id == recipient_id)
        )).scalars().first()
        assert handoff is not None and handoff.content == "please handle this"
