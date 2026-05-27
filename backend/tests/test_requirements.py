"""Requirements traceability — one test per challenge success criterion.

Maps the rubric's Functional Requirements directly to assertions so compliance is
auditable. Items that are genuinely UI-only or scheduled for a later phase are
`skip`ped with an explicit reason (not silently absent), so the report doubles as
a status matrix.

    Functional Requirements:
    - Agent CRUD: name, role, system prompt, model, tools, channels
    - Agent configuration: schedules, memory, skills, interaction rules, guardrails
    - Visual workflow builder with conditions and feedback loops
    - At least 2 pre-built workflow templates
    - External channel integration: WhatsApp, Telegram, or Slack
    - Live monitoring with real-time logs, inter-agent messages, token/cost tracking
    - Working end-to-end demo with 2+ agents executing a real task
"""

from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.repositories import AgentRepository, RunRepository, WorkflowRepository
from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.main import app
from app.observability.events import run_channel
from app.redis_client import get_redis
from app.runtime import queue
from app.runtime.engine import RunEngine


@pytest_asyncio.fixture
async def client(engine):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _engine() -> RunEngine:
    return RunEngine(
        session_factory=SessionFactory,
        provider=StubProvider(Script([]), strict=False),
        executor=HarnessExecutor(backoff_base_s=0),
    )


async def _run_to_completion(run_id: uuid.UUID) -> None:
    await _engine().run(run_id)


# ── Agent CRUD: name, role, system prompt, model, tools, channels ────────────


async def test_req_agent_crud_all_fields(client):
    body = {
        "name": "Req-Researcher",
        "role": "Web research specialist",
        "system_prompt": "Research thoroughly and cite sources.",
        "soul_md": "You are a careful, sourced researcher.",
        "persona": {"traits": ["rigorous"], "tone": "precise"},
        "model_provider": "anthropic",
        "model_name": "claude-sonnet-4-6",
        "tool_ids": ["web_search", "http_request"],
    }
    created = (await client.post("/agents", json=body)).json()
    fetched = (await client.get(f"/agents/{created['id']}")).json()
    # name, role, system prompt, model, tools all round-trip.
    assert fetched["name"] == "Req-Researcher"
    assert fetched["role"] == body["role"]
    assert fetched["system_prompt"] == body["system_prompt"]
    assert fetched["model_name"] == "claude-sonnet-4-6"
    assert fetched["tool_ids"] == ["web_search", "http_request"]
    assert fetched["soul_md"] and fetched["persona"]["traits"] == ["rigorous"]

    assert (await client.patch(f"/agents/{created['id']}", json={"role": "Lead"})).json()["role"] == "Lead"
    assert (await client.delete(f"/agents/{created['id']}")).status_code == 204


async def test_req_agent_channels(client):
    """The 'channels' dimension: connect an agent to a channel via a binding."""
    agent = (await client.post("/agents", json={"name": "Req-Bot", "role": "r", "system_prompt": "s"})).json()
    channel = (await client.post("/channels", json={"type": "telegram", "name": "req-bot", "config": {"bot_token": "x"}})).json()
    binding = (await client.post(f"/channels/{channel['id']}/bindings", json={"agent_id": agent["id"], "external_id": "chat-1"})).json()
    assert binding["agent_id"] == agent["id"]
    listed = (await client.get(f"/channels/{channel['id']}/bindings")).json()
    assert any(b["agent_id"] == agent["id"] for b in listed)


# ── Agent configuration: schedules, memory, skills, interaction rules, guardrails ──


async def test_req_agent_configuration_dimensions(client):
    body = {
        "name": "Req-Configured",
        "role": "r",
        "system_prompt": "interaction rules go here",   # interaction rules
        "tool_ids": ["python_exec"],                      # skills
        "memory_policy": {"strategy": "summary", "max_messages": 30},  # memory
        "guardrails": {"max_iterations": 5, "max_cost_per_run_usd": "0.25", "pii_redaction": True},  # guardrails
        "persona": {"traits": ["formal"], "tone": "neutral"},
    }
    a = (await client.post("/agents", json=body)).json()
    assert a["memory_policy"]["strategy"] == "summary"
    assert a["guardrails"]["max_cost_per_run_usd"] == "0.25"
    assert a["tool_ids"] == ["python_exec"]


@pytest.mark.skip(reason="Schedules API lands in Phase 7 (APScheduler); the schedules table exists in the data model.")
async def test_req_agent_schedules():
    ...


# ── Visual workflow builder: conditions and feedback loops ───────────────────


async def test_req_workflow_conditions_and_feedback_loop(client):
    """The builder UI is Phase 8, but the *capability* (conditional edges +
    feedback loops with termination) is exercised here against the engine."""
    async with SessionFactory() as s:
        drafter = await AgentRepository(s).create(name="ReqDrafter", role="r", system_prompt="s", model_provider="stub", model_name="stub")
        critic = await AgentRepository(s).create(name="ReqCritic", role="r", system_prompt="s", model_provider="stub", model_name="stub")
        graph = {
            "name": "ReqLoop", "entry_node": "drafter", "variables": {},
            "nodes": [
                {"id": "drafter", "type": "agent", "agent_id": str(drafter.id), "output_key": "draft"},
                {"id": "critic", "type": "agent", "agent_id": str(critic.id), "output_key": "critique"},
            ],
            "edges": [
                {"id": "e1", "from": "drafter", "to": "critic"},
                {"id": "e2", "from": "critic", "to": "drafter", "condition": "iteration_count < 4", "priority": 1},
            ],
        }
        wf = await WorkflowRepository(s).create(name="ReqLoop", graph=graph)
        run = await RunRepository(s).create(workflow_id=wf.id, workflow_version=1, trigger_type="manual", initial_state={"variables": {}})
        await s.commit()
        run_id, wf_id = run.id, wf.id

    await _run_to_completion(run_id)

    async with SessionFactory() as s:
        steps = [st.node_id for st in await RunRepository(s).steps_for_run(run_id)]
    # Feedback loop ran: drafter, critic, drafter, critic — then condition fails -> END.
    assert steps == ["drafter", "critic", "drafter", "critic"]


@pytest.mark.skip(reason="Visual builder UI (React Flow canvas) is Phase 8; graph schema + validation + execution are tested in test_validation/test_runtime.")
async def test_req_visual_builder_ui():
    ...


# ── At least 2 pre-built workflow templates ──────────────────────────────────


async def test_req_two_prebuilt_templates(client):
    from scripts.seed import main as seed_main

    await seed_main()
    workflows = (await client.get("/workflows")).json()
    names = {w["name"] for w in workflows}
    assert {"Market Briefing (demo)", "Draft & Critique (demo)"} <= names
    assert len([w for w in workflows if "(demo)" in w["name"]]) >= 2


# ── External channel integration: Telegram ───────────────────────────────────


async def test_req_telegram_channel_binding(client):
    channel = (await client.post("/channels", json={"type": "telegram", "name": "tg", "config": {"bot_token": "t"}})).json()
    assert channel["type"] == "telegram"
    # Binding resolution is the webhook routing entrypoint.
    async with SessionFactory() as s:
        from app.db.repositories import ChannelRepository
        await ChannelRepository(s).add_binding(channel_id=uuid.UUID(channel["id"]), external_id="chat-9")
        await s.commit()
        resolved = await ChannelRepository(s).resolve_binding(uuid.UUID(channel["id"]), "chat-9")
    assert resolved is not None


@pytest.mark.skip(reason="Live Telegram getUpdates/webhook delivery lands in Phase 6; the Channel abstraction + binding routing are in place.")
async def test_req_telegram_live_roundtrip():
    ...


# ── Live monitoring: real-time logs, inter-agent messages, token/cost tracking ──


async def test_req_live_monitoring_and_cost_tracking(client):
    # Build a 2-agent run.
    async with SessionFactory() as s:
        a1 = await AgentRepository(s).create(name="ReqMonA", role="r", system_prompt="s", model_provider="stub", model_name="claude-sonnet-4-5")
        a2 = await AgentRepository(s).create(name="ReqMonB", role="r", system_prompt="s", model_provider="stub", model_name="claude-sonnet-4-5")
        graph = {"name": "ReqMon", "entry_node": "a", "variables": {},
                 "nodes": [{"id": "a", "type": "agent", "agent_id": str(a1.id), "output_key": "x"},
                           {"id": "b", "type": "agent", "agent_id": str(a2.id), "output_key": "y"}],
                 "edges": [{"id": "e", "from": "a", "to": "b"}]}
        wf = await WorkflowRepository(s).create(name="ReqMon", graph=graph)
        run = await RunRepository(s).create(workflow_id=wf.id, workflow_version=1, trigger_type="manual", initial_state={"variables": {}})
        await s.commit()
        run_id = run.id

    # Subscribe to the live event channel, then run.
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(run_channel(run_id))
    await asyncio.sleep(0.05)

    await _run_to_completion(run_id)

    events = []
    for _ in range(40):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg and msg.get("type") == "message":
            events.append(json.loads(msg["data"])["type"])
    await pubsub.unsubscribe(run_channel(run_id))
    await pubsub.aclose()

    # Real-time events emitted (logs/monitoring).
    assert "run.started" in events and "step.completed" in events and "run.completed" in events
    # Token/cost tracking present and rolled up.
    detail = (await client.get(f"/runs/{run_id}")).json()
    assert Decimal(detail["total_cost_usd"]) > 0
    assert detail["total_tokens_out"] > 0
    # Per-step "logs" (messages) persisted and visible.
    assert len(detail["messages"]) >= 2


# ── Working end-to-end demo with 2+ agents executing a real task ─────────────


async def test_req_end_to_end_two_plus_agents(client):
    from scripts.seed import main as seed_main

    await seed_main()
    wfs = (await client.get("/workflows")).json()
    market = next(w for w in wfs if w["name"] == "Market Briefing (demo)")

    # Create + execute inline (rather than via the queue) so the test is
    # deterministic and doesn't race a live worker also consuming the stream.
    async with SessionFactory() as s:
        run = await RunRepository(s).create(
            workflow_id=uuid.UUID(market["id"]), workflow_version=market["current_version"],
            trigger_type="manual", initial_state={"variables": {"topic": "demo"}},
        )
        await s.commit()
        run_id = run.id
    await _run_to_completion(run_id)

    detail = (await client.get(f"/runs/{run_id}")).json()
    assert detail["status"] == "completed"
    assert [s["node_id"] for s in detail["steps"]] == ["researcher", "analyst", "briefer"]  # 3 agents
    assert Decimal(detail["total_cost_usd"]) > 0
