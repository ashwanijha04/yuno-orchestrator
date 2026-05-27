"""Worker entrypoint — consumes runs from the at-least-once queue and executes
them via the RunEngine. Crash between claim and ack re-delivers the run.
"""

from __future__ import annotations

import asyncio
import os
import signal

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from app.harness.config import get_provider
from app.logging import configure_logging, get_logger
from app.redis_client import close_redis, get_redis
from app.runtime import queue
from app.runtime.engine import RunEngine

log = get_logger("worker")
CONSUMER = os.environ.get("WORKER_NAME", f"worker-{os.getpid()}")


async def _check_dependencies() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await get_redis().ping()


def _build_engine(budget_cap_usd=None) -> RunEngine:
    return RunEngine(
        session_factory=SessionFactory, provider=get_provider(), budget_cap_usd=budget_cap_usd
    )


async def main() -> None:
    configure_logging()
    log.info("worker.starting", consumer=CONSUMER)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await _check_dependencies()
    await queue.ensure_group()
    log.info("worker.ready", stream=queue.STREAM, group=queue.GROUP)

    while not stop.is_set():
        try:
            batch = await queue.claim_batch(CONSUMER, count=1, block_ms=2000)
            for entry_id, run_id in batch:
                await _process(run_id)
                await queue.ack(entry_id)
        except Exception:  # noqa: BLE001 — keep the loop alive
            log.exception("worker.loop_error")
            await asyncio.sleep(1.0)

    await close_redis()
    log.info("worker.stopped")


async def _process(run_id: str) -> None:
    import uuid
    from decimal import Decimal

    from app.db.repositories import RunRepository

    log.info("worker.run.start", run_id=run_id)
    # Honor a per-run cost cap stashed in the trigger payload.
    cap = None
    async with SessionFactory() as s:
        run = await RunRepository(s).get(uuid.UUID(run_id))
        if run and run.trigger_payload and run.trigger_payload.get("max_cost_usd"):
            cap = Decimal(str(run.trigger_payload["max_cost_usd"]))
    eng = _build_engine(budget_cap_usd=cap)
    status = await eng.run(uuid.UUID(run_id))
    log.info("worker.run.done", run_id=run_id, status=status)


if __name__ == "__main__":
    asyncio.run(main())
