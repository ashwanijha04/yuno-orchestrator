"""LLM-as-judge evaluator — scores a run's output against rubric criteria.

Built on the same harness as everything else (routed provider + fallback, cost
tracking, JSON validation), so it's just another HarnessedCall — traceable,
replayable, and cheap to reason about.
"""

from __future__ import annotations

import json
from decimal import Decimal

from app.harness.call import BudgetTracker, LLMRequest, Message
from app.harness.config import build_harnessed_call, resolve_runtime
from app.harness.executor import HarnessExecutor
from app.harness.routing import resolve as resolve_routes
from app.logging import get_logger

log = get_logger("eval")

_CRITERIA = ("relevance", "correctness", "completeness")

JUDGE_SYSTEM = (
    "You are a strict, fair evaluator of an AI agent's output. Score how well the "
    "OUTPUT satisfies the TASK on each criterion from 0.0 to 1.0. Be concise and "
    "honest — reserve high scores for genuinely strong work.\n"
    "Reply with ONLY a JSON object of this exact shape:\n"
    '{"relevance": 0.0, "correctness": 0.0, "completeness": 0.0, '
    '"rationale": "one or two sentences"}'
)


def _parse(content: str) -> dict | None:
    """Pull the JSON object out of the judge's reply (tolerates code fences)."""
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def judge_run(task: str, output: str) -> dict:
    """Return {scores, overall, verdict, rationale, cost_usd}. Never raises —
    on failure returns a null evaluation so the caller can degrade gracefully."""
    if not output or not output.strip():
        return {"scores": {}, "overall": None, "verdict": None,
                "rationale": "No output to evaluate.", "cost_usd": Decimal("0")}

    candidates = resolve_routes(task_type="normal", explicit_provider=None, explicit_model=None)
    prompt = (
        f"TASK:\n{task or '(no task recorded)'}\n\n"
        f"OUTPUT:\n{output[:6000]}\n\n"
        "Score the OUTPUT now as the JSON object specified."
    )
    request = LLMRequest(
        model_provider="auto",
        model_name=candidates[0].model_name,
        system=JUDGE_SYSTEM,
        messages=[Message(role="user", content=prompt)],
        temperature=0.0,
        max_tokens=400,
        metadata={"kind": "eval.judge"},
    )
    call = build_harnessed_call(
        request=request, candidates=candidates,
        runtime=resolve_runtime(None, None), budget=BudgetTracker(cap_usd=None),
    )
    try:
        resp = await HarnessExecutor().execute(call)
    except Exception as exc:  # noqa: BLE001
        log.warning("eval.judge_failed", detail=str(exc))
        return {"scores": {}, "overall": None, "verdict": None,
                "rationale": f"Judge unavailable: {exc}", "cost_usd": Decimal("0")}

    data = _parse(resp.content) or {}
    scores = {c: _clamp(data.get(c)) for c in _CRITERIA if data.get(c) is not None}
    overall = round(sum(scores.values()) / len(scores), 3) if scores else None
    verdict = None if overall is None else ("pass" if overall >= 0.6 else "fail")
    return {
        "scores": scores,
        "overall": overall,
        "verdict": verdict,
        "rationale": str(data.get("rationale") or "")[:1000],
        "cost_usd": call.cost_usd,
    }


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
