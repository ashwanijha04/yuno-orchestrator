"""WebSocket gateway. A client subscribed to a run gets (1) a snapshot of what
already happened (replayed from Postgres — every event also lives there) then
(2) live events forwarded from the Redis run channel.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.repositories import RunRepository
from app.db.session import SessionFactory
from app.logging import get_logger
from app.observability.events import run_channel
from app.redis_client import get_redis

router = APIRouter(tags=["ws"])
log = get_logger("ws")


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: uuid.UUID):
    await websocket.accept()

    # 1) Snapshot from Postgres so a late or reconnecting client catches up.
    async with SessionFactory() as s:
        repo = RunRepository(s)
        run = await repo.get(run_id)
        if run is None:
            await websocket.send_json({"type": "error", "detail": "run not found"})
            await websocket.close()
            return
        steps = await repo.steps_for_run(run_id)
        messages = await repo.messages_for_run(run_id)
    await websocket.send_json(
        {
            "type": "snapshot",
            "run_id": str(run_id),
            "status": run.status,
            "total_cost_usd": str(run.total_cost_usd),
            "steps": [
                {"node_id": st.node_id, "status": st.status, "cost_usd": str(st.cost_usd),
                 "started_at": st.started_at.isoformat(),
                 "completed_at": st.completed_at.isoformat() if st.completed_at else None}
                for st in steps
            ],
            "messages": [
                {"role": m.role, "content": m.content, "agent_id": str(m.agent_id) if m.agent_id else None}
                for m in messages
            ],
        }
    )

    # 2) Live forward from Redis pub/sub.
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(run_channel(run_id))
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                await websocket.send_text(msg["data"])
            else:
                await asyncio.sleep(0.05)  # yield; also lets disconnects surface
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws.error", run_id=str(run_id), detail=str(exc))
    finally:
        await pubsub.unsubscribe(run_channel(run_id))
        await pubsub.aclose()
