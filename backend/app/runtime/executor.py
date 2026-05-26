"""Worker entrypoint.

Phase 0: boots, connects to Redis + Postgres, and idles on the run queue.
Phase 3 replaces the idle loop with: consume run from the at-least-once queue →
load workflow version → run outer graph → persist → emit events.
"""

from __future__ import annotations

import asyncio
import signal

from sqlalchemy import text

from app.db.session import engine
from app.logging import configure_logging, get_logger
from app.redis_client import close_redis, get_redis

log = get_logger("worker")

RUN_QUEUE = "yuno:runs"  # Redis Stream key (consumer group added in Phase 3)


async def _check_dependencies() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await get_redis().ping()
    log.info("worker.dependencies_ok")


async def main() -> None:
    configure_logging()
    log.info("worker.starting")
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await _check_dependencies()
    log.info("worker.ready", queue=RUN_QUEUE)

    # Placeholder idle loop until Phase 3 wires the real queue consumer.
    while not stop.is_set():
        await asyncio.sleep(1.0)

    await close_redis()
    log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
