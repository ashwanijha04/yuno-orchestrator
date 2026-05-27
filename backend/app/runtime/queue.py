"""At-least-once run queue on Redis Streams + consumer group.

A worker crash between dequeue and commit re-delivers the message (pending entries
list), so no run is silently lost. This is consistent with "Postgres is truth":
the stream only carries run ids; the run's state lives in Postgres.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.redis_client import get_redis

STREAM = "yuno:runs"
GROUP = "workers"


async def ensure_group(redis: Redis | None = None) -> None:
    redis = redis or get_redis()
    try:
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue_run(run_id: uuid.UUID | str, redis: Redis | None = None) -> str:
    redis = redis or get_redis()
    return await redis.xadd(STREAM, {"run_id": str(run_id)})


async def claim_batch(
    consumer: str, count: int = 1, block_ms: int = 5000, redis: Redis | None = None
) -> list[tuple[str, str]]:
    """Return [(entry_id, run_id)] of newly delivered runs for this consumer."""
    redis = redis or get_redis()
    resp = await redis.xreadgroup(
        GROUP, consumer, {STREAM: ">"}, count=count, block=block_ms
    )
    out: list[tuple[str, str]] = []
    for _stream, entries in resp or []:
        for entry_id, fields in entries:
            out.append((entry_id, fields["run_id"]))
    return out


async def ack(entry_id: str, redis: Redis | None = None) -> None:
    redis = redis or get_redis()
    await redis.xack(STREAM, GROUP, entry_id)


async def reclaim_stale(
    consumer: str, min_idle_ms: int = 30_000, redis: Redis | None = None
) -> list[tuple[str, str]]:
    """Re-deliver entries abandoned by a crashed worker (pending > min_idle)."""
    redis = redis or get_redis()
    _cursor, entries, _ = await redis.xautoclaim(
        STREAM, GROUP, consumer, min_idle_time=min_idle_ms, start_id="0", count=10
    )
    return [(eid, fields["run_id"]) for eid, fields in entries]
