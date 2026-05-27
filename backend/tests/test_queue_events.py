"""At-least-once queue roundtrip + event publish/subscribe (the plumbing the
live timeline depends on). Requires Redis."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest_asyncio

from app.observability.events import publish_event, run_channel
from app.redis_client import get_redis
from app.runtime import queue


@pytest_asyncio.fixture
async def fresh_stream():
    r = get_redis()
    await r.delete(queue.STREAM)
    await queue.ensure_group()
    yield
    await r.delete(queue.STREAM)


async def test_queue_enqueue_claim_ack(fresh_stream):
    run_id = uuid.uuid4()
    await queue.enqueue_run(run_id)

    batch = await queue.claim_batch("c1", count=10, block_ms=500)
    assert (str(run_id)) in [rid for _eid, rid in batch]

    for entry_id, _rid in batch:
        await queue.ack(entry_id)

    # Nothing new to deliver after ack.
    assert await queue.claim_batch("c1", count=10, block_ms=200) == []


async def test_event_publish_subscribe():
    run_id = uuid.uuid4()
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(run_channel(run_id))
    await asyncio.sleep(0.05)  # let subscription register

    await publish_event(run_id, "step.started", {"node_id": "main"})

    received = None
    for _ in range(20):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if msg and msg.get("type") == "message":
            received = json.loads(msg["data"])
            break
    await pubsub.unsubscribe(run_channel(run_id))
    await pubsub.aclose()

    assert received is not None
    assert received["type"] == "step.started"
    assert received["node_id"] == "main"
