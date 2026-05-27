"""Worker entrypoint. Runs three concurrent loops:
  1. run queue consumer (at-least-once) -> RunEngine
  2. outbox dispatcher -> delivers pending channel messages
  3. Telegram poller (dev) -> getUpdates -> inbound runs

Crash between claim and ack re-delivers the run.
"""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from decimal import Decimal

from sqlalchemy import select, text

from app.channels import build_channel
from app.channels.dispatcher import dispatch_pending
from app.channels.inbound import handle_inbound
from app.config import settings
from app.db.models import Channel
from app.db.repositories import RunRepository
from app.db.session import SessionFactory, engine
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


async def _process(run_id: str) -> None:
    cap = None
    async with SessionFactory() as s:
        run = await RunRepository(s).get(uuid.UUID(run_id))
        if run and run.trigger_payload and run.trigger_payload.get("max_cost_usd"):
            cap = Decimal(str(run.trigger_payload["max_cost_usd"]))
    # provider=None -> ModelRouter resolves per agent (task_type routing + fallback).
    eng = RunEngine(session_factory=SessionFactory, budget_cap_usd=cap)
    status = await eng.run(uuid.UUID(run_id))
    log.info("worker.run.done", run_id=run_id, status=status)


async def _consume_loop(stop: asyncio.Event) -> None:
    await queue.ensure_group()
    while not stop.is_set():
        try:
            for entry_id, run_id in await queue.claim_batch(CONSUMER, count=1, block_ms=2000):
                await _process(run_id)
                await queue.ack(entry_id)
        except Exception:  # noqa: BLE001
            log.exception("worker.consume_error")
            await asyncio.sleep(1.0)


async def _outbox_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await dispatch_pending(SessionFactory)
        except Exception:  # noqa: BLE001
            log.exception("worker.outbox_error")
        await asyncio.sleep(2.0)


async def _scheduler_loop(stop: asyncio.Event) -> None:
    """Fire due cron schedules: enqueue a run, advance next_run_at."""
    from app.db.repositories import RunRepository, ScheduleRepository, WorkflowRepository

    while not stop.is_set():
        try:
            async with SessionFactory() as s:
                sched_repo = ScheduleRepository(s)
                due = await sched_repo.due()
                for sched in due:
                    wf = await WorkflowRepository(s).get(sched.workflow_id)
                    if wf is None:
                        continue
                    run = await RunRepository(s).create(
                        workflow_id=sched.workflow_id, workflow_version=wf.current_version,
                        trigger_type="schedule", trigger_payload=sched.payload or {},
                        initial_state={"variables": sched.payload or {}},
                    )
                    await sched_repo.mark_fired(sched)
                    await s.commit()
                    await queue.enqueue_run(run.id)
                    log.info("scheduler.fired", schedule_id=str(sched.id), run_id=str(run.id))
        except Exception:  # noqa: BLE001
            log.exception("worker.scheduler_error")
        await asyncio.sleep(15.0)


async def _telegram_poll_loop(stop: asyncio.Event) -> None:
    if settings.telegram_transport != "polling":
        return
    offsets: dict[str, int] = {}
    while not stop.is_set():
        try:
            async with SessionFactory() as s:
                channels = (
                    await s.execute(select(Channel).where(Channel.type == "telegram", Channel.status == "active"))
                ).scalars().all()
                channel_specs = [(str(c.id), c.config or {}) for c in channels]
            polled = False
            for cid, config in channel_specs:
                if not config.get("bot_token"):
                    continue
                polled = True
                adapter = build_channel(cid, "telegram", config)
                updates = await adapter.get_updates(offset=offsets.get(cid), timeout=20)
                for update_id, inbound in updates:
                    offsets[cid] = update_id + 1
                    await handle_inbound(inbound, SessionFactory)
            if not polled:
                await asyncio.sleep(5.0)
        except Exception:  # noqa: BLE001
            log.exception("worker.telegram_poll_error")
            await asyncio.sleep(5.0)


async def main() -> None:
    configure_logging()
    log.info("worker.starting", consumer=CONSUMER, telegram_transport=settings.telegram_transport)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await _check_dependencies()
    log.info("worker.ready", stream=queue.STREAM, group=queue.GROUP)

    tasks = [
        asyncio.create_task(_consume_loop(stop)),
        asyncio.create_task(_outbox_loop(stop)),
        asyncio.create_task(_scheduler_loop(stop)),
        asyncio.create_task(_telegram_poll_loop(stop)),
    ]
    await stop.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_redis()
    log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
