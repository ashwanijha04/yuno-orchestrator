"""Phase 3 end-to-end runtime tests: workflow execution + persistence + cost
roll-up, conditional routing, and loop termination. Real Postgres + a scripted
StubProvider so behaviour is deterministic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select, text

from app.db.models import Step
from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.runtime.engine import RunEngine

_TABLES = "messages, steps, runs, workflow_versions, workflows, agents, channel_bindings, channels"


@pytest_asyncio.fixture
async def clean_db(engine):
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    yield


async def _make_agent(name: str, model_name: str = "stub") -> str:
    async with SessionFactory() as s:
        agent = await AgentRepository(s).create(
            name=name, role="r", system_prompt="do the thing",
            model_provider="stub", model_name=model_name,
            memory_policy={}, guardrails={"max_iterations": 3}, harness={},
        )
        await s.commit()
        return str(agent.id)


async def _make_workflow(graph: dict) -> str:
    async with SessionFactory() as s:
        wf = await WorkflowRepository(s).create(name=graph["name"], graph=graph)
        await s.commit()
        return str(wf.id)


async def _make_run(workflow_id: str, variables: dict) -> str:
    async with SessionFactory() as s:
        run = await RunRepository(s).create(
            workflow_id=workflow_id, workflow_version=1, trigger_type="manual",
            initial_state={"variables": variables},
        )
        await s.commit()
        return str(run.id)


def _engine(script: Script, **kw) -> RunEngine:
    return RunEngine(
        session_factory=SessionFactory,
        provider=StubProvider(script),
        executor=HarnessExecutor(backoff_base_s=0),
        **kw,
    )


async def _step_node_ids(run_id: str) -> list[str]:
    async with SessionFactory() as s:
        rows = (await s.execute(select(Step).where(Step.run_id == run_id).order_by(Step.started_at))).scalars().all()
        return [r.node_id for r in rows]


# ── tests ────────────────────────────────────────────────────────────────────


async def test_workflow_execution_two_agents(clean_db):
    researcher = await _make_agent("Researcher", model_name="claude-sonnet-4-5")
    briefer = await _make_agent("Briefer", model_name="claude-sonnet-4-5")
    graph = {
        "name": "Linear",
        "entry_node": "researcher",
        "variables": {"topic": {"type": "string"}},
        "nodes": [
            {"id": "researcher", "type": "agent", "agent_id": researcher, "output_key": "research"},
            {"id": "briefer", "type": "agent", "agent_id": briefer, "output_key": "brief"},
        ],
        "edges": [{"id": "e1", "from": "researcher", "to": "briefer"}],
    }
    wf = await _make_workflow(graph)
    run_id = await _make_run(wf, {"topic": "OpenAI"})

    script = Script(
        [
            {"match": {"call_index": 0}, "response": {"content": "found 3 sources", "tokens_in": 100, "tokens_out": 20}},
            {"match": {"call_index": 1}, "response": {"content": "your brief", "tokens_in": 50, "tokens_out": 10}},
        ]
    )
    status = await _engine(script).run(run_id)

    assert status == "completed"
    assert await _step_node_ids(run_id) == ["researcher", "briefer"]

    async with SessionFactory() as s:
        repo = RunRepository(s)
        run = await repo.get(run_id)
        assert run.status == "completed"
        assert run.total_tokens_in == 150
        assert run.total_tokens_out == 30
        # Cost rolls up from messages: sonnet 0.003/0.015 per 1k.
        assert run.total_cost_usd == Decimal("0.000900")
        msgs = await repo.messages_for_run(run_id)
        assert [m.content for m in msgs] == ["found 3 sources", "your brief"]
        assert run.final_state["artifacts"] == {"research": "found 3 sources", "brief": "your brief"}


async def test_conditional_routing_takes_matching_branch(clean_db):
    classifier = await _make_agent("Classifier")
    refund = await _make_agent("RefundHandler")
    general = await _make_agent("GeneralHandler")
    graph = {
        "name": "Router",
        "entry_node": "classifier",
        "variables": {},
        "nodes": [
            {"id": "classifier", "type": "agent", "agent_id": classifier, "output_key": "category"},
            {"id": "refund", "type": "agent", "agent_id": refund, "output_key": "out"},
            {"id": "general", "type": "agent", "agent_id": general, "output_key": "out"},
        ],
        "edges": [
            {"id": "e1", "from": "classifier", "to": "refund", "condition": 'artifacts.category == "refund"', "priority": 1},
            {"id": "e2", "from": "classifier", "to": "general", "priority": 2},
        ],
    }
    wf = await _make_workflow(graph)

    # Run 1 -> classifier says "refund" -> refund branch.
    run1 = await _make_run(wf, {})
    script1 = Script([
        {"match": {"call_index": 0}, "response": {"content": "refund"}},
        {"match": {"call_index": 1}, "response": {"content": "refund processed"}},
    ])
    assert await _engine(script1).run(run1) == "completed"
    assert await _step_node_ids(run1) == ["classifier", "refund"]

    # Run 2 -> classifier says "other" -> general fallback branch.
    run2 = await _make_run(wf, {})
    script2 = Script([
        {"match": {"call_index": 0}, "response": {"content": "other"}},
        {"match": {"call_index": 1}, "response": {"content": "general reply"}},
    ])
    assert await _engine(script2).run(run2) == "completed"
    assert await _step_node_ids(run2) == ["classifier", "general"]


async def test_loop_terminates_on_iteration_count(clean_db):
    looper = await _make_agent("Looper")
    graph = {
        "name": "Loop",
        "entry_node": "a",
        "variables": {},
        "nodes": [{"id": "a", "type": "agent", "agent_id": looper, "output_key": "x"}],
        # Self-loop while iteration_count < 3; otherwise the router returns END.
        "edges": [{"id": "e1", "from": "a", "to": "a", "condition": "iteration_count < 3", "priority": 1}],
    }
    wf = await _make_workflow(graph)
    run_id = await _make_run(wf, {})

    script = Script([{"match": {}, "response": {"content": f"tick {i}"}} for i in range(6)])
    assert await _engine(script).run(run_id) == "completed"
    # Runs at count 0->1, 1->2, 2->3; at 3 the condition fails -> 3 executions.
    assert await _step_node_ids(run_id) == ["a", "a", "a"]
