"""Run engine — executes one run end to end.

Loads the workflow version, compiles the outer graph, and drives it. Each agent
node runs its inner ReAct loop through the harness and persists steps/messages
(commit) then publishes events (Redis). Persistence is the source of truth; the
events are best-effort live transport.
"""

from __future__ import annotations

import uuid
from typing import Any

from decimal import Decimal
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Agent
from app.db.repositories import RunRepository, WorkflowRepository
from app.harness.call import BudgetTracker
from app.harness.config import resolve_runtime
from app.harness.executor import HarnessExecutor
from app.logging import get_logger
from app.observability.events import publish_event
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.inner import ToolRuntime, run_agent_loop
from app.runtime.outer import build_outer_graph, recursion_limit_for
from app.runtime.state import GraphState, initial_state
from sqlalchemy import select

log = get_logger("engine")


class RunEngine:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        provider: Any = None,  # None -> ModelRouter picks per agent (live); tests inject a stub
        *,
        executor: HarnessExecutor | None = None,
        budget_cap_usd: Decimal | None = None,
        tool_runtime: ToolRuntime | None = None,
    ):
        self.session_factory = session_factory
        self.provider = provider
        self.executor = executor or HarnessExecutor()
        self.budget = BudgetTracker(cap_usd=budget_cap_usd)
        # Default tool runtime so granted tools execute; tests can inject their own.
        if tool_runtime is None:
            from app.tools.runtime import ToolRuntime

            tool_runtime = ToolRuntime(session_factory)
        self.tool_runtime = tool_runtime

    async def run(self, run_id: uuid.UUID) -> str:
        graph, agents = await self._load(run_id)
        # Guardrail: if no explicit run budget, derive the cost circuit-breaker
        # from the tightest per-agent guardrails.max_cost_per_run_usd.
        if self.budget.cap_usd is None:
            caps = [
                Decimal(str(a["guardrails"]["max_cost_per_run_usd"]))
                for a in agents.values()
                if a.get("guardrails", {}).get("max_cost_per_run_usd")
            ]
            if caps:
                self.budget.cap_usd = min(caps)
        await self._mark_running(run_id)
        await publish_event(run_id, "run.started", {})

        node_runner = self._make_node_runner(run_id, agents)
        compiled = build_outer_graph(graph, node_runner)

        try:
            variables = (await self._get_run_variables(run_id)) or {}
            final = await compiled.ainvoke(
                initial_state(str(run_id), variables),
                config={"recursion_limit": recursion_limit_for(graph)},
            )
            await self._finalize(run_id, "completed", final_state=_serializable(final))
            await self._maybe_auto_reply(run_id, final)
            await publish_event(run_id, "run.completed", {})
            return "completed"
        except Exception as exc:  # noqa: BLE001 — surface failure on the run row
            log.exception("run.failed", run_id=str(run_id))
            await self._finalize(run_id, "failed", error=str(exc))
            await publish_event(run_id, "run.failed", {"error": str(exc)})
            return "failed"

    # ── node execution ───────────────────────────────────────────────────────

    def _make_node_runner(self, run_id: uuid.UUID, agents: dict[str, dict]):
        async def node_runner(node: dict, state: GraphState) -> dict:
            node_type = node.get("type", "agent")
            if node_type == "agent":
                return await self._run_agent_node(run_id, node, state, agents)
            if node_type == "condition":
                return {}  # pure routing; handled by outgoing conditional edges
            if node_type == "channel_out":
                return await self._run_channel_out(run_id, node, state)
            # Stubbed node types (transform/human/parallel/channel_in).
            return {"metadata": {f"skipped_{node['id']}": node_type}}

        return node_runner

    async def _run_agent_node(
        self, run_id: uuid.UUID, node: dict, state: GraphState, agents: dict[str, dict]
    ) -> dict:
        agent = agents[str(node["agent_id"])]
        node_id = node["id"]

        # Resolve this node's input slice from state.
        agent_input = _resolve_input(node.get("input_mapping"), state, agent)

        # Step row at start (commit) -> publish started.
        async with self.session_factory() as s:
            repo = RunRepository(s)
            step = await repo.add_step(run_id, node_id=node_id, agent_id=agent["id"], status="running")
            step_id = step.id
            await s.commit()
        await publish_event(run_id, "step.started", {"node_id": node_id, "agent": agent["name"], "step_id": str(step_id)})

        # Memory: query the agent's strategy for context to inject (queried, not pushed).
        prior_messages = await self._load_memory(run_id, agent)

        # Inner reasoning loop (no DB).
        harness_runtime = self._resolve_harness(agent, node)
        result = await run_agent_loop(
            executor=self.executor,
            provider=self.provider,
            agent=agent,
            harness_runtime=harness_runtime,
            agent_input=agent_input,
            budget=self.budget,
            run_id=run_id,
            tool_runtime=self.tool_runtime,
            prior_messages=prior_messages,
        )

        # Persist messages + complete step (commit) -> publish completed.
        async with self.session_factory() as s:
            repo = RunRepository(s)
            for m in result.messages:
                await repo.add_message(
                    run_id, role=m.role, content=m.content, step_id=step_id,
                    cost_usd=m.cost_usd, tokens_in=m.tokens_in, tokens_out=m.tokens_out,
                    agent_id=agent["id"], tool_calls=m.tool_calls,
                )
            status = "failed" if result.blocked_reason and "max_iterations" in (result.blocked_reason or "") else "completed"
            await repo.complete_step(step_id, status=status, error=result.blocked_reason)
            await s.commit()
        await publish_event(
            run_id, "step.completed",
            {"node_id": node_id, "agent": agent["name"], "step_id": str(step_id),
             "cost_usd": str(result.cost_usd), "blocked": result.blocked_reason},
        )

        update: dict = {
            "current_agent": node_id,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "messages": [{"agent_id": str(agent["id"]), "role": "assistant", "content": result.content}],
        }
        output_key = node.get("output_key")
        if output_key:
            update["artifacts"] = {output_key: result.content}
        return update

    async def _run_channel_out(self, run_id: uuid.UUID, node: dict, state: GraphState) -> dict:
        # Phase 5 wires the outbox; here we record the intent as a message.
        content = state.get("messages", [{}])[-1].get("content", "") if state.get("messages") else ""
        async with self.session_factory() as s:
            repo = RunRepository(s)
            await repo.add_message(run_id, role="system", content=f"[channel_out] {content}")
            await s.commit()
        await publish_event(run_id, "channel_out", {"node_id": node["id"]})
        return {}

    # ── helpers ────────────────────────────────────────────────────────────────

    def _resolve_harness(self, agent: dict, node: dict):
        return resolve_runtime(agent.get("harness"), node.get("harness_overrides"))

    async def _load_memory(self, run_id: uuid.UUID, agent: dict) -> list[dict]:
        from app.memory import MemoryContext, get_memory_strategy

        async with self.session_factory() as s:
            run = await RunRepository(s).get(run_id)
            tp = (run.trigger_payload or {}) if run else {}
            # Chat turns share a conversation_id: inject the prior turns regardless
            # of the agent's configured strategy (a chat must remember context).
            if tp.get("conversation_id"):
                try:
                    return await self._load_conversation(s, tp["conversation_id"], run_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning("memory.conversation_load_failed", detail=str(exc))
                    return []
            strategy = get_memory_strategy(agent.get("memory_policy"))
            ctx = MemoryContext(run_id=str(run_id), channel_external_id=tp.get("external_id"))
            try:
                return await strategy.load(agent["id"], ctx, s)
            except Exception as exc:  # noqa: BLE001 — memory is best-effort
                log.warning("memory.load_failed", detail=str(exc))
                return []

    async def _load_conversation(self, s, conversation_id: str, current_run_id: uuid.UUID, limit: int = 20) -> list[dict]:
        """Prior user/assistant turns of this chat, across earlier runs."""
        from app.db.models import Message, Run

        run_ids = (
            await s.execute(
                select(Run.id).where(
                    Run.trigger_payload["conversation_id"].astext == conversation_id,
                    Run.id != current_run_id,
                )
            )
        ).scalars().all()
        if not run_ids:
            return []
        rows = (
            await s.execute(
                select(Message)
                .where(Message.run_id.in_(run_ids), Message.role.in_(("user", "assistant")))
                .order_by(Message.ts.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]

    async def _load(self, run_id: uuid.UUID) -> tuple[dict, dict[str, dict]]:
        async with self.session_factory() as s:
            run = await RunRepository(s).get(run_id)
            if run is None:
                raise ValueError(f"run {run_id} not found")
            version = await WorkflowRepository(s).get_version(run.workflow_id, run.workflow_version)
            if version is None:
                raise ValueError("workflow version not found")
            graph = version.graph
            agent_ids = {str(n["agent_id"]) for n in graph["nodes"] if n.get("type", "agent") == "agent"}
            agents: dict[str, dict] = {}
            if agent_ids:
                rows = (await s.execute(select(Agent).where(Agent.id.in_([uuid.UUID(a) for a in agent_ids])))).scalars().all()
                agents = {str(a.id): AgentRuntime.from_model(a).as_dict() for a in rows}
            return graph, agents

    async def _get_run_variables(self, run_id: uuid.UUID) -> dict | None:
        async with self.session_factory() as s:
            run = await RunRepository(s).get(run_id)
            if run is None:
                return None
            return (run.initial_state or {}).get("variables") or (run.trigger_payload or {})

    async def _mark_running(self, run_id: uuid.UUID) -> None:
        async with self.session_factory() as s:
            await RunRepository(s).set_status(run_id, "running")
            await s.commit()

    async def _finalize(self, run_id: uuid.UUID, status: str, error: str | None = None, final_state: dict | None = None) -> None:
        async with self.session_factory() as s:
            await RunRepository(s).set_status(run_id, status, error=error, final_state=final_state)
            await s.commit()

    async def _maybe_auto_reply(self, run_id: uuid.UUID, final: GraphState) -> None:
        """For channel-triggered runs, queue the final output back to the chat
        via the outbox so the conversation feels natural."""
        from app.db.models import OutboundMessage

        async with self.session_factory() as s:
            run = await RunRepository(s).get(run_id)
            if not run or run.trigger_type != "channel" or not run.trigger_payload:
                return
            channel_id = run.trigger_payload.get("channel_id")
            external_id = run.trigger_payload.get("external_id")
            artifacts = final.get("artifacts", {}) if final else {}
            reply = list(artifacts.values())[-1] if artifacts else None
            if not reply:
                msgs = await RunRepository(s).messages_for_run(run_id)
                reply = msgs[-1].content if msgs else None
            if channel_id and external_id and reply:
                s.add(OutboundMessage(
                    channel_id=uuid.UUID(channel_id), external_id=external_id,
                    content=str(reply), status="pending",
                ))
                await s.commit()


def _resolve_input(input_mapping: dict | None, state: GraphState, agent: dict) -> Any:
    """Resolve a node's declared input slice from state via simple $.path refs."""
    if not input_mapping:
        # Default: the last message if any, else the run variables.
        messages = state.get("messages", [])
        if messages:
            return messages[-1].get("content", "")
        return state.get("variables", {})
    resolved: dict[str, Any] = {}
    for key, ref in input_mapping.items():
        resolved[key] = _resolve_ref(ref, state)
    return resolved


def _resolve_ref(ref: str, state: GraphState) -> Any:
    # Supports "$.variables.x" / "$.artifacts.y"; literals pass through.
    if not isinstance(ref, str) or not ref.startswith("$."):
        return ref
    parts = ref[2:].split(".")
    cur: Any = {
        "variables": state.get("variables", {}),
        "artifacts": state.get("artifacts", {}),
    }
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _serializable(state: GraphState) -> dict:
    return {
        "artifacts": state.get("artifacts", {}),
        "iteration_count": state.get("iteration_count", 0),
        "current_agent": state.get("current_agent"),
        "message_count": len(state.get("messages", [])),
    }
