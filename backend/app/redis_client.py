"""Shared Redis client (pub/sub transport, queue, rate limits, agent inbox).

Redis is transport, not truth — see the architecture invariants. A single
connection pool per process; callers get a client via `get_redis()`.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.config import settings

_pool: redis.ConnectionPool | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=_pool)


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
