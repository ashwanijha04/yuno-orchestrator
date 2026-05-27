"""Channel registry — maps a channel type to its adapter."""

from __future__ import annotations

from app.channels.base import Channel
from app.channels.stubs import SlackChannel, WhatsAppChannel
from app.channels.telegram import TelegramChannel

_REGISTRY = {
    "telegram": TelegramChannel,
    "slack": SlackChannel,
    "whatsapp": WhatsAppChannel,
}


def build_channel(channel_id: str, type: str, config: dict) -> Channel:
    cls = _REGISTRY.get(type)
    if cls is None:
        raise ValueError(f"unknown channel type {type!r}")
    return cls(channel_id, config)
