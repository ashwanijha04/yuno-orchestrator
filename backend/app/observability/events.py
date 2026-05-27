"""Run event publishing. The worker publishes to Redis AFTER the Postgres commit
(never before — see invariant #2), and the WS gateway forwards to UI clients.
Every event is also reconstructable from Postgres, so dropped clients replay.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.logging import get_logger
from app.redis_client import get_redis

log = get_logger("events")


def run_channel(run_id: uuid.UUID | str) -> str:
    return f"channel:run:{run_id}"


async def publish_event(run_id: uuid.UUID | str, event_type: str, payload: dict[str, Any]) -> None:
    """Publish a run event. Best-effort: if Redis is down the run still proceeds
    (the UI degrades to polling Postgres)."""
    event = {
        "type": event_type,
        "run_id": str(run_id),
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }
    try:
        await get_redis().publish(run_channel(run_id), json.dumps(event, default=str))
    except Exception as exc:  # noqa: BLE001 — events are best-effort transport
        log.warning("events.publish_failed", run_id=str(run_id), detail=str(exc))
