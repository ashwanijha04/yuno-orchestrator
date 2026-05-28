"""coding_session — run a real Claude Code session on the user's machine.

Enqueues a job for the host-side bridge (scripts/claude_bridge.py), which runs
the local `claude --dangerously-skip-permissions` CLI (using the user's own
Claude auth — no API key) and posts the result back. The tool waits for that
result. If no bridge is running, it times out with a clear hint.
"""

from __future__ import annotations

import asyncio
import uuid

from app.redis_client import get_redis
from app.tools.base import ToolContext

PENDING = "coding:pending"
_POLL_S = 2
_TIMEOUT_S = 900  # claude sessions can take a while


class CodingSessionTool:
    name = "coding_session"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        task = str(input.get("task", "")).strip()
        cwd = str(input.get("cwd", "") or "").strip()
        if not task:
            return {"error": "task is required (describe what to build/change)"}

        r = get_redis()
        sid = uuid.uuid4().hex
        key = f"coding:session:{sid}"
        await r.hset(key, mapping={"task": task, "cwd": cwd, "status": "pending", "result": ""})
        await r.expire(key, 3600)
        await r.rpush(PENDING, sid)

        waited = 0
        while waited < _TIMEOUT_S:
            await asyncio.sleep(_POLL_S)
            waited += _POLL_S
            status = await r.hget(key, "status")
            if status in ("done", "failed"):
                result = await r.hget(key, "result")
                return {"status": status, "result": result or "", "session_id": sid}

        await r.hset(key, "status", "timeout")
        return {
            "error": "No coding bridge picked this up. In your local terminal run "
            "`python scripts/claude_bridge.py` (where the `claude` CLI is installed), then retry.",
        }
