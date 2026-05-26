"""Phase 2 harness tests: stub/replay providers, cost math (Decimal), and the
executor's retry / validation-reinject / cost-cap / fatal-propagation behaviour."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.harness.call import (
    BudgetTracker,
    HarnessedCall,
    LLMRequest,
    Message,
)
from app.harness.cost import get_cost_model
from app.harness.executor import HarnessExecutor
from app.harness.interceptors import CostCapInterceptor, InterceptorDecision, TraceInterceptor
from app.harness.providers import FatalError, ReplayProvider, Script, StubProvider
from app.harness.providers.replay import RecordedCall, ReplayExhaustedError
from app.harness.validators import JSONSchemaValidator, MaxLengthValidator


def _req(text: str = "hello", model: str = "stub", **meta) -> LLMRequest:
    return LLMRequest(
        model_provider="stub",
        model_name=model,
        messages=[Message(role="user", content=text)],
        metadata=meta,
    )


def _call(provider, *, validators=None, interceptors=None, budget=None, model="stub") -> HarnessedCall:
    return HarnessedCall(
        request=_req(model=model, agent_id="researcher"),
        provider=provider,
        cost_model=get_cost_model(model),
        validators=validators or [],
        interceptors=interceptors or [],
        budget=budget or BudgetTracker(),
    )


# ── Cost model ───────────────────────────────────────────────────────────────


def test_cost_model_is_exact_decimal():
    model = get_cost_model("claude-sonnet-4-5")  # 0.003 in, 0.015 out per 1k
    assert model.cost(1000, 1000) == Decimal("0.018000")
    assert model.cost(250, 60) == Decimal("0.001650")
    assert isinstance(model.cost(1, 1), Decimal)


def test_unknown_model_uses_conservative_default():
    model = get_cost_model("some-future-model")
    assert model.cost(0, 1000) == Decimal("0.075000")  # errs high


# ── Stub provider ────────────────────────────────────────────────────────────


async def test_stub_resolves_by_agent_and_call_index():
    script = Script(
        [
            {"match": {"agent_id": "researcher", "call_index": 0}, "response": {"content": "first"}},
            {"match": {"agent_id": "researcher", "call_index": 1}, "response": {"content": "second"}},
        ]
    )
    stub = StubProvider(script)
    r0 = await stub.complete(_req(agent_id="researcher"))
    r1 = await stub.complete(_req(agent_id="researcher"))
    assert (r0.content, r1.content) == ("first", "second")


async def test_stub_tool_calls_and_strict_miss():
    script = Script(
        [{"match": {}, "response": {"content": "", "tool_calls": [{"name": "web_search", "input": {"q": "x"}}]}}]
    )
    stub = StubProvider(script, strict=True)
    resp = await stub.complete(_req(agent_id="researcher"))
    assert resp.tool_calls[0].name == "web_search"
    with pytest.raises(FatalError):
        await stub.complete(_req(agent_id="researcher"))  # no more entries


# ── Replay provider ──────────────────────────────────────────────────────────


async def test_replay_sequence_and_exhaustion():
    calls = [
        RecordedCall(request={}, response={"content": "a", "tokens_out": 5}),
        RecordedCall(request={}, response={"content": "b", "tokens_out": 7}),
    ]
    replay = ReplayProvider(calls)
    assert (await replay.complete(_req())).content == "a"
    assert (await replay.complete(_req())).content == "b"
    with pytest.raises(ReplayExhaustedError):
        await replay.complete(_req())


# ── Executor ─────────────────────────────────────────────────────────────────


async def test_executor_success_computes_cost():
    script = Script([{"match": {}, "response": {"content": "ok", "tokens_in": 1000, "tokens_out": 1000}}])
    call = _call(StubProvider(script), model="claude-sonnet-4-5")
    resp = await HarnessExecutor(backoff_base_s=0).execute(call)
    assert resp.content == "ok"
    assert call.cost_usd == Decimal("0.018000")
    assert len(call.attempts) == 1


async def test_executor_retries_then_succeeds():
    script = Script(
        [
            {"match": {}, "raises": "retryable"},
            {"match": {}, "response": {"content": "recovered"}},
        ]
    )
    call = _call(StubProvider(script))
    resp = await HarnessExecutor(backoff_base_s=0).execute(call)
    assert resp.content == "recovered"
    assert len(call.attempts) == 2


async def test_executor_exhausts_retries_and_raises():
    from app.harness.providers.base import RetryableError

    script = Script([{"match": {}, "raises": "retryable"} for _ in range(5)])
    call = _call(StubProvider(script))
    call.max_attempts = 3
    with pytest.raises(RetryableError):
        await HarnessExecutor(backoff_base_s=0).execute(call)
    assert len(call.attempts) == 3


async def test_executor_fatal_propagates_immediately():
    script = Script([{"match": {}, "raises": "fatal"}])
    call = _call(StubProvider(script))
    with pytest.raises(FatalError):
        await HarnessExecutor(backoff_base_s=0).execute(call)
    assert len(call.attempts) == 1


async def test_json_validator_reinjects_and_recovers():
    script = Script(
        [
            {"match": {}, "response": {"content": "not json"}},
            {"match": {}, "response": {"content": '{"approved": true}'}},
        ]
    )
    call = _call(
        StubProvider(script),
        validators=[JSONSchemaValidator(schema={"required": ["approved"]})],
    )
    resp = await HarnessExecutor(backoff_base_s=0).execute(call)
    assert resp.content == '{"approved": true}'
    assert len(call.attempts) == 2
    # The corrective message was appended for the retry.
    assert any("failed validation" in m.content for m in call.request.messages if isinstance(m.content, str))


async def test_max_length_validator_truncates_without_retry():
    script = Script([{"match": {}, "response": {"content": "x" * 100}}])
    call = _call(StubProvider(script), validators=[MaxLengthValidator(max_chars=10)])
    resp = await HarnessExecutor(backoff_base_s=0).execute(call)
    assert len(resp.content) == 10
    assert len(call.attempts) == 1


async def test_cost_cap_blocks_before_provider_call():
    # Strict stub with an empty script would raise if called — so reaching a
    # non-raising blocked response proves the provider was never invoked.
    call = _call(
        StubProvider(Script([]), strict=True),
        interceptors=[CostCapInterceptor()],
        budget=BudgetTracker(cap_usd=Decimal("0.00001")),
        model="claude-opus-4-7",
    )
    resp = await HarnessExecutor(backoff_base_s=0).execute(call)
    assert resp.finish_reason == "blocked"
    assert call.blocked_reason is not None
    assert call.cost_usd == Decimal("0")
    assert call.attempts == []


async def test_cost_cap_accumulates_spend():
    script = Script([{"match": {}, "response": {"content": "ok", "tokens_out": 1000}}])
    budget = BudgetTracker(cap_usd=Decimal("1.00"))
    call = _call(StubProvider(script), interceptors=[CostCapInterceptor()], budget=budget, model="claude-sonnet-4-5")
    await HarnessExecutor(backoff_base_s=0).execute(call)
    assert budget.spent_usd == Decimal("0.015000")


async def test_interceptor_before_after_run_in_order():
    events: list[str] = []

    class Recorder:
        name = "recorder"

        def __init__(self, tag):
            self.tag = tag

        async def before(self, call):
            events.append(f"before:{self.tag}")
            return InterceptorDecision(action="continue")

        async def after(self, call):
            events.append(f"after:{self.tag}")

    script = Script([{"match": {}, "response": {"content": "ok"}}])
    call = _call(StubProvider(script), interceptors=[Recorder("a"), Recorder("b")])
    await HarnessExecutor(backoff_base_s=0).execute(call)
    assert events == ["before:a", "before:b", "after:a", "after:b"]
