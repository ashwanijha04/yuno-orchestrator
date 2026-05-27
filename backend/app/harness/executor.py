"""HarnessExecutor — the one path every LLM call flows through.

Lifecycle: interceptor `before` (block/modify) → for each provider candidate
(model-routing fallback chain): retry loop + validation → on success, `after` and
return; on fatal/exhausted, fall back to the next candidate. No `if testing:` —
behaviour is a function of the providers, validators, and interceptors on the call.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal

from app.harness.call import Attempt, HarnessedCall, LLMResponse, ProviderCandidate
from app.harness.providers.base import FatalError, RetryableError


class HarnessExecutor:
    def __init__(self, backoff_base_s: float = 0.1):
        # backoff_base_s=0 disables sleeps (tests).
        self.backoff_base_s = backoff_base_s

    async def execute(self, call: HarnessedCall) -> LLMResponse:
        # Phase 1 — pre-flight interceptors (once, regardless of candidate).
        for icx in call.interceptors:
            decision = await icx.before(call)
            if decision.action == "block":
                return await self._finish_blocked(call, decision.reason or "blocked")
            if decision.action == "modify" and decision.modified_request is not None:
                call.request = decision.modified_request

        candidates = call.candidates or [
            ProviderCandidate(call.provider, call.request.model_name, call.cost_model)
        ]

        # Phase 2 — try each candidate in order (model-routing fallback chain).
        last_exc: Exception | None = None
        for candidate in candidates:
            call.provider = candidate.provider
            call.cost_model = candidate.cost_model
            call.request.model_name = candidate.model_name
            call.response = None
            try:
                await self._run_candidate(call)
            except (FatalError, RetryableError) as exc:
                last_exc = exc
                continue  # fall back to the next provider
            await self._run_after(call)
            return call.response

        await self._run_after(call)
        raise last_exc or RetryableError("all provider candidates failed")

    async def _run_candidate(self, call: HarnessedCall) -> None:
        """Retry + validate against the active provider. Sets call.response/cost on
        success; raises FatalError (immediately) or RetryableError (exhausted)."""
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
                raise
            except RetryableError as exc:
                attempt.error = str(exc)
                attempt.latency_ms = int((time.monotonic() - t0) * 1000)
                call.attempts.append(attempt)
                last_exc = exc
                if attempt_num < call.max_attempts - 1:
                    await self._backoff(attempt_num)
                    continue
                raise

            attempt.latency_ms = int((time.monotonic() - t0) * 1000)
            attempt.raw_response = response.raw

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

            call.attempts.append(attempt)
            call.response = response
            call.cost_usd = call.cost_model.cost(response.tokens_in, response.tokens_out)
            return

        raise last_exc or RetryableError("exhausted attempts without a response")

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
