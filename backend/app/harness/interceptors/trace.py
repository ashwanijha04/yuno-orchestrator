"""Structured-log tracing for every call. OpenTelemetry spans layer on in
Phase 7; for now this binds ids and emits start/finish log lines."""

from __future__ import annotations

import time

from app.harness.call import HarnessedCall
from app.harness.interceptors.base import InterceptorDecision
from app.logging import get_logger

log = get_logger("harness")


class TraceInterceptor:
    name = "trace"

    def __init__(self):
        self._start: dict = {}

    async def before(self, call: HarnessedCall) -> InterceptorDecision:
        self._start[call.call_id] = time.monotonic()
        log.info(
            "llm.call.start",
            call_id=str(call.call_id),
            run_id=str(call.run_id) if call.run_id else None,
            agent_id=str(call.agent_id) if call.agent_id else None,
            provider=call.provider.name,
            model=call.request.model_name,
        )
        return InterceptorDecision(action="continue")

    async def after(self, call: HarnessedCall) -> None:
        started = self._start.pop(call.call_id, None)
        elapsed_ms = int((time.monotonic() - started) * 1000) if started else None
        log.info(
            "llm.call.finish",
            call_id=str(call.call_id),
            attempts=len(call.attempts),
            tokens_in=call.response.tokens_in if call.response else 0,
            tokens_out=call.response.tokens_out if call.response else 0,
            cost_usd=str(call.cost_usd),
            blocked=call.blocked_reason,
            elapsed_ms=elapsed_ms,
        )
