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
SEEN = "coding:bridge_seen"
_POLL_S = 2
_TIMEOUT_S = 900   # claude sessions can take a while
_GONE_S = 24       # bridge considered gone after this long with no heartbeat
_NO_BRIDGE_HINT = (
    "No coding bridge is connected on this machine. Start it with `make up` "
    "(it auto-launches) or `python3 scripts/claude_bridge.py`, then retry."
)


class CodingSessionTool:
    name = "coding_session"

    async def _cancelled(self, ctx: ToolContext) -> bool:
        if ctx.run_id is None:
            return False
        from app.db.repositories import RunRepository

        async with ctx.session_factory() as s:
            run = await RunRepository(s).get(ctx.run_id)
            return run is not None and run.status == "cancelled"

    async def execute(self, input: dict, ctx: ToolContext) -> dict:
        task = str(input.get("task", "")).strip()
        cwd = str(input.get("cwd", "") or "").strip()
        if not task:
            return {"error": "task is required (describe what to build/change)"}

        r = get_redis()
        # Fail fast: don't enqueue + block for minutes if no bridge is even running.
        if not await r.exists(SEEN):
            return {"error": _NO_BRIDGE_HINT}

        sid = uuid.uuid4().hex
        key = f"coding:session:{sid}"
        await r.hset(key, mapping={"task": task, "cwd": cwd, "status": "pending", "result": ""})
        await r.expire(key, 3600)
        await r.rpush(PENDING, sid)

        waited = 0
        gone = 0
        while waited < _TIMEOUT_S:
            await asyncio.sleep(_POLL_S)
            waited += _POLL_S
            status = await r.hget(key, "status")
            if status in ("done", "failed"):
                return {"status": status, "result": await r.hget(key, "result") or "", "session_id": sid}
            if await self._cancelled(ctx):
                await r.hset(key, "status", "cancelled")
                return {"status": "cancelled", "result": "Stopped by user."}
            gone = 0 if await r.exists(SEEN) else gone + _POLL_S
            if gone >= _GONE_S:
                await r.hset(key, "status", "failed")
                return {"error": "The coding bridge disconnected. " + _NO_BRIDGE_HINT}

        await r.hset(key, "status", "timeout")
        return {"error": "Coding session timed out."}
