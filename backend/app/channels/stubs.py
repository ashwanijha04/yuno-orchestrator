"""Slack and WhatsApp stubs — present to prove the Channel abstraction. To make
either real: implement send/parse_webhook/health_check here (Slack: signing-secret
verification + chat.postMessage; WhatsApp: Cloud API), register in the registry,
add a config form. No orchestrator changes.
"""

from __future__ import annotations

from app.channels.base import ChannelHealth, InboundMessage


class _StubChannel:
    type = "stub"

    def __init__(self, channel_id: str, config: dict):
        self.channel_id = channel_id
        self.config = config

    async def send(self, external_id: str, content: str) -> str:
        raise NotImplementedError(f"{self.type} send not implemented (stub)")

    def parse_webhook(self, headers: dict, body: bytes) -> InboundMessage | None:
        return None

    async def health_check(self) -> ChannelHealth:
        return ChannelHealth(ok=False, detail=f"{self.type} is a stub")


class SlackChannel(_StubChannel):
    type = "slack"


class WhatsAppChannel(_StubChannel):
    type = "whatsapp"
