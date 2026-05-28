"""Coding sessions — bridge endpoints.

A coding session runs your LOCAL `claude` CLI (Claude Code), not an API model.
Because the platform is containerised and `claude` is authenticated on your host,
a small host-side bridge (scripts/claude_bridge.py) polls /coding/next, runs
`claude --dangerously-skip-permissions` locally, and posts the result back here.
Jobs are carried over Redis (transport), so the in-process tool and the bridge
never touch each other directly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.redis_client import get_redis

router = APIRouter(prefix="/coding", tags=["coding"])

PENDING = "coding:pending"
SEEN = "coding:bridge_seen"  # heartbeat: set on each bridge poll, short TTL


def _key(session_id: str) -> str:
    return f"coding:session:{session_id}"


class NextJob(BaseModel):
    id: str
    task: str
    cwd: str = ""


class ResultIn(BaseModel):
    result: str
    ok: bool = True


@router.get("/status")
async def status():
    """Whether a host coding bridge has polled recently (cockpit indicator)."""
    return {"connected": bool(await get_redis().exists(SEEN))}


@router.get("/next")
async def claim_next():
    """The host bridge calls this to claim the next pending coding job (204 if none)."""
    r = get_redis()
    await r.set(SEEN, "1", ex=12)  # heartbeat — the bridge polls every ~2s
    sid = await r.lpop(PENDING)
    if not sid:
        return Response(status_code=204)
    await r.hset(_key(sid), "status", "running")
    data = await r.hgetall(_key(sid))
    return NextJob(id=sid, task=data.get("task", ""), cwd=data.get("cwd", ""))


@router.post("/{session_id}/result")
async def submit_result(session_id: str, body: ResultIn):
    """The host bridge posts the result of running `claude` here."""
    r = get_redis()
    if not await r.exists(_key(session_id)):
        raise HTTPException(404, "unknown coding session")
    await r.hset(_key(session_id), mapping={
        "status": "done" if body.ok else "failed",
        "result": (body.result or "")[:30000],
    })
    return {"ok": True}
