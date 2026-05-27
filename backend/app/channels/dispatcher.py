"""Outbox dispatcher — delivers pending outbound_messages to their channels.

Reads `outbound_messages` where status='pending', loads the channel adapter, and
sends. On failure, increments attempts with a cap (then marks failed). This is the
delivery half of the transactional outbox: the agent's send writes the row in its
own transaction; this loop guarantees at-least-once delivery without coupling the
run to the channel API being up.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.channels import build_channel
from app.db.models import Channel, OutboundMessage
from app.logging import get_logger

log = get_logger("channels.dispatcher")
MAX_ATTEMPTS = 5


async def dispatch_pending(session_factory: async_sessionmaker, limit: int = 20) -> int:
    """Process up to `limit` pending outbound messages. Returns count attempted."""
    async with session_factory() as s:
        pending = (
            await s.execute(
                select(OutboundMessage).where(OutboundMessage.status == "pending").limit(limit)
            )
        ).scalars().all()
        if not pending:
            return 0
        # Cache channels by id.
        channels: dict = {}
        for msg in pending:
            if msg.channel_id not in channels:
                channels[msg.channel_id] = await s.get(Channel, msg.channel_id)

        for msg in pending:
            channel = channels.get(msg.channel_id)
            if channel is None:
                msg.status = "failed"
                msg.last_error = "channel missing"
                continue
            adapter = build_channel(str(channel.id), channel.type, channel.config or {})
            try:
                await adapter.send(msg.external_id, msg.content)
                msg.status = "sent"
                msg.sent_at = datetime.now(UTC)
            except Exception as exc:  # noqa: BLE001
                msg.attempts += 1
                msg.last_error = str(exc)
                if msg.attempts >= MAX_ATTEMPTS:
                    msg.status = "failed"
                log.warning("outbox.send_failed", id=str(msg.id), attempts=msg.attempts, detail=str(exc))
        await s.commit()
        return len(pending)
