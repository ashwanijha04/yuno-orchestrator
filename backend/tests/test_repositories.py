"""Phase 1 critical-path tests: agent CRUD, workflow versioning, run cost
roll-up, channel binding resolution."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.repositories import (
    AgentRepository,
    ChannelRepository,
    RunRepository,
    WorkflowRepository,
)

AGENT_FIELDS = dict(
    name="Researcher",
    role="Web research specialist",
    system_prompt="You research topics thoroughly.",
    model_provider="anthropic",
    model_name="claude-sonnet-4-5",
    tool_ids=["web_search"],
    memory_policy={"strategy": "buffer", "max_messages": 20},
    guardrails={"max_iterations": 5},
    harness={"max_attempts": 3, "validators": [{"type": "json_schema"}]},
)


async def test_agent_lifecycle(session):
    repo = AgentRepository(session)

    created = await repo.create(**AGENT_FIELDS)
    assert created.id is not None
    assert created.harness["max_attempts"] == 3

    fetched = await repo.get(created.id)
    assert fetched is not None and fetched.name == "Researcher"
    assert await repo.get_by_name("Researcher") is not None
    assert len(await repo.list()) == 1

    updated = await repo.update(created.id, role="Senior research lead")
    assert updated is not None and updated.role == "Senior research lead"

    assert await repo.delete(created.id) is True
    assert await repo.get(created.id) is None


async def test_workflow_versioning(session):
    repo = WorkflowRepository(session)
    graph_v1 = {"entry_node": "a", "nodes": [{"id": "a", "type": "agent"}], "edges": []}
    graph_v2 = {"entry_node": "a", "nodes": [{"id": "a", "type": "agent"}, {"id": "b", "type": "agent"}], "edges": []}

    wf = await repo.create(name="Market Intel", graph=graph_v1, description="demo")
    assert wf.current_version == 1
    assert await repo.get_current_graph(wf.id) == graph_v1

    v2 = await repo.new_version(wf.id, graph_v2)
    assert v2 is not None and v2.version == 2

    refreshed = await repo.get(wf.id)
    assert refreshed.current_version == 2
    # Old version is immutable and still retrievable.
    assert (await repo.get_version(wf.id, 1)).graph == graph_v1
    assert await repo.get_current_graph(wf.id) == graph_v2


async def test_run_cost_rollup(session):
    wf_repo = WorkflowRepository(session)
    run_repo = RunRepository(session)
    wf = await wf_repo.create(name="WF", graph={"entry_node": "a", "nodes": [], "edges": []})

    run = await run_repo.create(
        workflow_id=wf.id, workflow_version=1, trigger_type="manual"
    )
    step = await run_repo.add_step(run.id, node_id="a", agent_id=None)

    await run_repo.add_message(
        run.id, role="assistant", content="hi", step_id=step.id,
        cost_usd=Decimal("0.012"), tokens_in=100, tokens_out=20,
    )
    await run_repo.add_message(
        run.id, role="assistant", content="more", step_id=step.id,
        cost_usd=Decimal("0.008"), tokens_in=50, tokens_out=10,
    )

    refreshed_run = await run_repo.get(run.id)
    assert refreshed_run.total_cost_usd == Decimal("0.020000")
    assert refreshed_run.total_tokens_in == 150
    assert refreshed_run.total_tokens_out == 30

    completed = await run_repo.set_status(run.id, "completed", final_state={"ok": True})
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert len(await run_repo.messages_for_run(run.id)) == 2


async def test_channel_binding_resolution(session):
    wf_repo = WorkflowRepository(session)
    ch_repo = ChannelRepository(session)
    wf = await wf_repo.create(name="WF2", graph={"entry_node": "a", "nodes": [], "edges": []})

    channel = await ch_repo.create(type="telegram", name="demo-bot", config={"bot_token": "x"})
    await ch_repo.add_binding(
        channel_id=channel.id, external_id="chat-42", workflow_id=wf.id
    )

    resolved = await ch_repo.resolve_binding(channel.id, "chat-42")
    assert resolved is not None and resolved.workflow_id == wf.id
    assert await ch_repo.resolve_binding(channel.id, "nonexistent") is None


@pytest.mark.parametrize("missing", ["agents", "workflows"])
async def test_get_missing_returns_none(session, missing):
    import uuid

    if missing == "agents":
        assert await AgentRepository(session).get(uuid.uuid4()) is None
    else:
        assert await WorkflowRepository(session).get(uuid.uuid4()) is None
