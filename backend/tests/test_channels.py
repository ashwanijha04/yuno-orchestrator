"""Phase 6: Telegram parse/verify + full channel roundtrip (inbound -> run ->
auto-reply outbox -> dispatch)."""

from __future__ import annotations

import json
import uuid

import pytest_asyncio
from sqlalchemy import select

from app.channels.base import InboundMessage
from app.channels.dispatcher import dispatch_pending
from app.channels.inbound import handle_inbound
from app.channels.telegram import TelegramChannel
from app.db.models import OutboundMessage
from app.db.repositories import AgentRepository, ChannelRepository
from app.db.session import SessionFactory
from app.harness.executor import HarnessExecutor
from app.harness.providers import Script, StubProvider
from app.runtime.engine import RunEngine


@pytest_asyncio.fixture
async def clean(engine):
    yield


def test_telegram_parse_and_secret_verify():
    body = json.dumps({"update_id": 1, "message": {"chat": {"id": 42}, "from": {"username": "al"}, "text": "hi"}}).encode()
    ch = TelegramChannel("cid", {"bot_token": "t"})
    inbound = ch.parse_webhook({}, body)
    assert inbound and inbound.external_id == "42" and inbound.content == "hi"

    secured = TelegramChannel("cid", {"bot_token": "t", "webhook_secret": "s3cret"})
    assert secured.parse_webhook({}, body) is None  # missing secret -> rejected
    assert secured.parse_webhook({"x-telegram-bot-api-secret-token": "s3cret"}, body).content == "hi"
    assert ch.parse_webhook({}, b"{}") is None  # non-message update -> None


async def test_channel_roundtrip(clean, monkeypatch):
    async with SessionFactory() as s:
        agent = await AgentRepository(s).create(
            name="ChatBot", role="assistant", system_prompt="Be helpful.",
            model_provider="stub", model_name="stub",
        )
        channel = await ChannelRepository(s).create(type="telegram", name="bot", config={"bot_token": "t"})
        # Wildcard binding: the bot serves any chat.
        await ChannelRepository(s).add_binding(channel_id=channel.id, external_id="*", agent_id=agent.id)
        await s.commit()
        channel_id = str(channel.id)

    # Inbound message -> resolves binding -> enqueues a channel run.
    inbound = InboundMessage(channel_id=channel_id, external_id="chat-9", content="hello bot")
    run_id = await handle_inbound(inbound, SessionFactory)
    assert run_id is not None

    async with SessionFactory() as s:
        from app.db.repositories import RunRepository
        run = await RunRepository(s).get(run_id)
        assert run.trigger_type == "channel" and run.trigger_payload["external_id"] == "chat-9"

    # Execute the run (stub) -> auto-reply queues an outbound message.
    engine = RunEngine(session_factory=SessionFactory, provider=StubProvider(Script([]), strict=False), executor=HarnessExecutor(backoff_base_s=0))
    assert await engine.run(run_id) == "completed"

    async with SessionFactory() as s:
        outbound = (await s.execute(select(OutboundMessage).where(OutboundMessage.external_id == "chat-9"))).scalars().all()
    assert len(outbound) >= 1 and outbound[0].status == "pending"

    # Dispatch with the channel send mocked -> marked sent.
    sent: list[tuple[str, str]] = []

    class FakeAdapter:
        async def send(self, external_id: str, content: str) -> str:
            sent.append((external_id, content))
            return "mid-1"

    monkeypatch.setattr("app.channels.dispatcher.build_channel", lambda *a, **k: FakeAdapter())
    await dispatch_pending(SessionFactory)

    assert sent and sent[0][0] == "chat-9"
    async with SessionFactory() as s:
        ob = (await s.execute(select(OutboundMessage).where(OutboundMessage.external_id == "chat-9"))).scalars().first()
    assert ob.status == "sent"
