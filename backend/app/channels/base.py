"""Channel protocol — a bidirectional messaging integration.

The control plane never imports a provider SDK; it calls `channel.send()` and
`channel.parse_webhook()`. Adding Slack = implement SlackChannel + register it;
no orchestrator changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class InboundMessage:
    channel_id: str
    external_id: str          # sender chat id
    content: str
    sender_name: str | None = None
    raw: dict = field(default_factory=dict)
    received_at: datetime | None = None


@dataclass
class ChannelHealth:
    ok: bool
    detail: str | None = None


@runtime_checkable
class Channel(Protocol):
    type: str

    async def send(self, external_id: str, content: str) -> str:
        """Send a message; returns a provider message id."""
        ...

    def parse_webhook(self, headers: dict, body: bytes) -> InboundMessage | None:
        """Verify + parse a webhook payload; None if invalid."""
        ...

    async def health_check(self) -> ChannelHealth: ...
