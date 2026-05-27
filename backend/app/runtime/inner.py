"""Inner agent reasoning loop — a structured ReAct loop that runs through the
harness. prepare -> (llm -> router -> tool)* -> end, with the guardrail/iteration
chokepoint at the router. Every LLM turn and tool call is returned for the engine
to persist, so the timeline reflects exactly what ran.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable

from app.harness.call import BudgetTracker, LLMRequest, Message
from app.harness.config import HarnessRuntime, build_harnessed_call
from app.harness.executor import HarnessExecutor
from app.runtime.persona import compose_system_prompt

# A tool runtime: given (name, input, context) -> result dict. Wired in Phase 5.
ToolRuntime = Callable[[str, dict, dict], Awaitable[dict]]


@dataclass
class PersistedMessage:
    role: str
    content: str
    cost_usd: Decimal = Decimal("0")
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: list[dict] | None = None
    tool_name: str | None = None


@dataclass
class InnerResult:
    content: str
    cost_usd: Decimal = Decimal("0")
    tokens_in: int = 0
    tokens_out: int = 0
    iterations: int = 0
    blocked_reason: str | None = None
    messages: list[PersistedMessage] = field(default_factory=list)


def _render_input(inp: Any) -> str:
    if isinstance(inp, str):
        return inp
    if isinstance(inp, dict):
        return "\n".join(f"{k}: {v}" for k, v in inp.items())
    return str(inp)


async def run_agent_loop(
    *,
    executor: HarnessExecutor,
    provider: Any,
    agent: dict,
    harness_runtime: HarnessRuntime,
    agent_input: Any,
    budget: BudgetTracker,
    run_id: uuid.UUID,
    tool_runtime: ToolRuntime | None = None,
    prior_messages: list[dict] | None = None,
) -> InnerResult:
    """Run one agent to completion. `agent` is the agent config row (as dict);
    `harness_runtime` is the resolved HarnessRuntime (max_attempts + validators +
    interceptors). `prior_messages` are memory-loaded messages to inject first."""
    guardrails = agent.get("guardrails", {})
    max_iter = int(guardrails.get("max_iterations", 10))
    effective_system = compose_system_prompt(agent)

    conversation: list[Message] = [
        Message(role=m["role"], content=m["content"]) for m in (prior_messages or [])
    ]
    conversation.append(Message(role="user", content=_render_input(agent_input)))
    result = InnerResult(content="")

    for i in range(max_iter):
        result.iterations = i + 1
        request = LLMRequest(
            model_provider=agent["model_provider"],
            model_name=agent["model_name"],
            system=effective_system,
            messages=list(conversation),
            tools=agent.get("tool_schemas", []),
            temperature=float(agent.get("temperature", 0.7)),
            max_tokens=int(agent.get("max_tokens", 2048)),
            metadata={"agent_id": str(agent.get("id", "")), "run_id": str(run_id)},
        )
        call = build_harnessed_call(
            request=request,
            provider=provider,
            runtime=harness_runtime,
            budget=budget,
            run_id=run_id,
            agent_id=agent.get("id"),
        )
        response = await executor.execute(call)

        result.cost_usd += call.cost_usd
        result.tokens_in += response.tokens_in
        result.tokens_out += response.tokens_out
        result.messages.append(
            PersistedMessage(
                role="assistant",
                content=response.content,
                cost_usd=call.cost_usd,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                tool_calls=[{"name": tc.name, "input": tc.input} for tc in response.tool_calls] or None,
            )
        )

        if call.blocked_reason:  # cost cap / guardrail tripped
            result.blocked_reason = call.blocked_reason
            result.content = response.content
            return result

        if response.tool_calls and tool_runtime is not None:
            conversation.append(Message(role="assistant", content=response.content or "(tool call)"))
            for tc in response.tool_calls:
                tool_out = await tool_runtime(
                    tc.name, tc.input, {"run_id": str(run_id), "agent_id": str(agent.get("id") or "")}
                )
                result.messages.append(
                    PersistedMessage(role="tool", content=str(tool_out), tool_name=tc.name)
                )
                conversation.append(Message(role="user", content=f"[tool {tc.name} result] {tool_out}"))
            continue  # loop back for the next reasoning turn

        result.content = response.content
        return result

    # Iteration cap hit without a final answer.
    result.blocked_reason = f"max_iterations ({max_iter}) reached"
    return result
