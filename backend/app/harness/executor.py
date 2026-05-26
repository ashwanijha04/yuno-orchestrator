"""HarnessExecutor — the one path every LLM call flows through.

Six phases: (1) interceptor `before` (block/modify), (2) execute with retry on
transient + validation failures, (3) validate, (4) normalize success, (5)
interceptor `after`, (6) persistence/emit (an interceptor concern, wired later).
No `if testing:` — behaviour is entirely a function of the providers, validators,
and interceptors on the call.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal

from app.harness.call import Attempt, HarnessedCall, LLMResponse
from app.harness.providers.base import FatalError, RetryableError


class HarnessExecutor:
    def __init__(self, backoff_base_s: float = 0.1):
        # backoff_base_s=0 disables sleeps (tests).
        self.backoff_base_s = backoff_base_s

    async def execute(self, call: HarnessedCall) -> LLMResponse:
        # Phase 1 — pre-flight interceptors.
        for icx in call.interceptors:
            decision = await icx.before(call)
            if decision.action == "block":
                return await self._finish_blocked(call, decision.reason or "blocked")
            if decision.action == "modify" and decision.modified_request is not None:
                call.request = decision.modified_request

        # Phases 2–4 — execute with retry, validate, normalize.
        last_exc: Exception | None = None
        for attempt_num in range(call.max_attempts):
            attempt = Attempt(num=attempt_num, started_at=datetime.now(UTC))
            t0 = time.monotonic()
            try:
                response = await call.provider.complete(call.request)
            except FatalError as exc:
                attempt.error = str(exc)
                attempt.latency_ms = int((time.monotonic() - t0) * 1000)
                call.attempts.append(attempt)
                await self._run_after(call)
                raise
            except RetryableError as exc:
                attempt.error = str(exc)
                attempt.latency_ms = int((time.monotonic() - t0) * 1000)
                call.attempts.append(attempt)
                last_exc = exc
                if attempt_num < call.max_attempts - 1:
                    await self._backoff(attempt_num)
                    continue
                break

            attempt.latency_ms = int((time.monotonic() - t0) * 1000)
            attempt.raw_response = response.raw

            # Phase 3 — validate.
            retry_failures = []
            for validator in call.validators:
                result = validator.validate(response, call.request)
                call.validation_results.append(result)
                if not result.passed and validator.allows_retry:
                    retry_failures.append((validator, result))

            if retry_failures and attempt_num < call.max_attempts - 1:
                for validator, result in retry_failures:
                    call.request = validator.reinject(call.request, result)
                attempt.validation_failures = [r.detail or "" for _, r in retry_failures]
                call.attempts.append(attempt)
                continue

            # Phase 4 — success.
            call.attempts.append(attempt)
            call.response = response
            call.cost_usd = call.cost_model.cost(response.tokens_in, response.tokens_out)
            break

        if call.response is None:
            await self._run_after(call)
            raise last_exc or RetryableError("exhausted attempts without a response")

        # Phase 5 — post-flight interceptors.
        await self._run_after(call)
        return call.response

    async def _finish_blocked(self, call: HarnessedCall, reason: str) -> LLMResponse:
        call.blocked_reason = reason
        call.cost_usd = Decimal("0")
        call.response = LLMResponse(content=f"[blocked: {reason}]", finish_reason="blocked")
        await self._run_after(call)
        return call.response

    async def _run_after(self, call: HarnessedCall) -> None:
        for icx in call.interceptors:
            await icx.after(call)

    async def _backoff(self, attempt_num: int) -> None:
        if self.backoff_base_s > 0:
            await asyncio.sleep(self.backoff_base_s * (2**attempt_num))
