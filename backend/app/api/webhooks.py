"""Channel webhooks. POST /webhooks/{channel_id} parses + verifies the payload,
resolves the binding, enqueues a run, and returns 200 immediately (async)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import build_channel
from app.channels.inbound import handle_inbound
from app.db.repositories import ChannelRepository
from app.db.session import SessionFactory, get_session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{channel_id}")
async def channel_webhook(channel_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)):
    channel = await ChannelRepository(session).get(channel_id)
    if channel is None:
        raise HTTPException(404, "channel not found")

    adapter = build_channel(str(channel_id), channel.type, channel.config or {})
    body = await request.body()
    inbound = adapter.parse_webhook(dict(request.headers), body)
    if inbound is None:
        # Bad signature or non-message update — ack without creating a run.
        return {"status": "ignored"}

    run_id = await handle_inbound(inbound, SessionFactory)
    return {"status": "accepted", "run_id": str(run_id) if run_id else None}
