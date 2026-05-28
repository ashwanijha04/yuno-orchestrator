"""Coding sessions — bridge endpoints.

A coding session runs your LOCAL `claude` CLI (Claude Code), not an API model.
Because the platform is containerised and `claude` is authenticated on your host,
a small host-side bridge (scripts/claude_bridge.py) polls /coding/next, runs
`claude --dangerously-skip-permissions` locally, and posts the result back here.
Jobs are carried over Redis (transport), so the in-process tool and the bridge
never touch each other directly.
"""

from __future__ import annotations

import uuid

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


class PlanIn(BaseModel):
    plan: str


class DecisionIn(BaseModel):
    decision: str  # allow | deny


class ApprovalOut(BaseModel):
    id: str
    task: str
    plan: str


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


@router.get("/approvals", response_model=list[ApprovalOut])
async def pending_approvals():
    """Coding sessions awaiting plan approval (cockpit cards)."""
    r = get_redis()
    out: list[ApprovalOut] = []
    for sid in await r.lrange("coding:awaiting", 0, -1):
        d = await r.hgetall(_key(sid))
        if d.get("status") == "awaiting_approval" and d.get("decision", "pending") == "pending":
            out.append(ApprovalOut(id=sid, task=d.get("task", ""), plan=d.get("plan", "")))
    return out


@router.post("/{session_id}/plan")
async def submit_plan(session_id: str, body: PlanIn):
    """Bridge posts Claude's PLAN; we surface it for approval (Telegram + cockpit)."""
    r = get_redis()
    key = _key(session_id)
    if not await r.exists(key):
        raise HTTPException(404, "unknown coding session")
    await r.hset(key, mapping={"plan": body.plan[:8000], "status": "awaiting_approval", "decision": "pending"})
    await r.rpush("coding:awaiting", session_id)
    d = await r.hgetall(key)
    ch, ext = d.get("notify_channel"), d.get("notify_external")
    if ch and ext:  # originated from a chat channel (e.g. Telegram) — ask there
        await r.set(f"coding:awaiting_chat:{ch}:{ext}", session_id, ex=3600)
        from app.db.models import OutboundMessage
        from app.db.session import SessionFactory

        text = (f"🔐 Plan for: {d.get('task', '')[:120]}\n\n{body.plan[:1400]}\n\n"
                "Reply /allow to run it, or /deny.")
        async with SessionFactory() as s:
            s.add(OutboundMessage(channel_id=uuid.UUID(ch), external_id=ext, content=text, status="pending"))
            await s.commit()
    return {"ok": True}


@router.post("/{session_id}/decide")
async def decide(session_id: str, body: DecisionIn):
    """Approve/deny a plan — from the cockpit or (via /allow //deny) Telegram."""
    r = get_redis()
    if not await r.exists(_key(session_id)):
        raise HTTPException(404, "unknown coding session")
    dec = "allow" if body.decision == "allow" else "deny"
    await r.hset(_key(session_id), "decision", dec)
    await r.lrem("coding:awaiting", 0, session_id)
    return {"ok": True, "decision": dec}


@router.get("/{session_id}")
async def get_session(session_id: str):
    """The bridge polls this for the approval decision + status."""
    d = await get_redis().hgetall(_key(session_id))
    if not d:
        raise HTTPException(404, "unknown coding session")
    return {"id": session_id, "status": d.get("status"), "decision": d.get("decision", "pending"),
            "result": d.get("result", "")}


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
