"""Telegram channel adapter (Bot API over httpx).

- send: sendMessage
- parse_webhook: verify the secret token header, extract chat id + text
- get_updates: long-polling (getUpdates) for friction-free local dev
- set_webhook: register the webhook URL for the snappier production path
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from app.channels.base import ChannelHealth, InboundMessage


class TelegramChannel:
    type = "telegram"

    def __init__(self, channel_id: str, config: dict):
        self.channel_id = channel_id
        self.token = config.get("bot_token") or ""
        self.webhook_secret = config.get("webhook_secret")

    @property
    def _base(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    async def send(self, external_id: str, content: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/sendMessage", json={"chat_id": external_id, "text": content}
            )
            resp.raise_for_status()
            return str(resp.json().get("result", {}).get("message_id", ""))

    def parse_webhook(self, headers: dict, body: bytes) -> InboundMessage | None:
        if self.webhook_secret:
            token = headers.get("x-telegram-bot-api-secret-token") or headers.get(
                "X-Telegram-Bot-Api-Secret-Token"
            )
            if token != self.webhook_secret:
                return None
        try:
            update = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return None
        return self._inbound_from_update(update)

    def _inbound_from_update(self, update: dict) -> InboundMessage | None:
        msg = update.get("message") or update.get("edited_message")
        if not msg or "text" not in msg:
            return None
        chat = msg.get("chat", {})
        frm = msg.get("from", {})
        return InboundMessage(
            channel_id=self.channel_id,
            external_id=str(chat.get("id")),
            content=msg["text"],
            sender_name=frm.get("username") or frm.get("first_name"),
            raw=update,
            received_at=datetime.now(UTC),
        )

    async def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[tuple[int, InboundMessage]]:
        """Long-poll. Returns [(update_id, InboundMessage)] for text messages."""
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            resp = await client.get(
                f"{self._base}/getUpdates",
                params={"timeout": timeout, **({"offset": offset} if offset is not None else {})},
            )
            resp.raise_for_status()
            data = resp.json()
        out: list[tuple[int, InboundMessage]] = []
        for upd in data.get("result", []):
            inbound = self._inbound_from_update(upd)
            if inbound:
                out.append((upd["update_id"], inbound))
        return out

    async def set_webhook(self, url: str) -> bool:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/setWebhook",
                json={"url": url, **({"secret_token": self.webhook_secret} if self.webhook_secret else {})},
            )
            return resp.status_code == 200 and resp.json().get("ok", False)

    async def health_check(self) -> ChannelHealth:
        if not self.token:
            return ChannelHealth(ok=False, detail="no bot_token configured")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base}/getMe")
            return ChannelHealth(ok=resp.status_code == 200, detail=None if resp.status_code == 200 else resp.text)
        except httpx.HTTPError as exc:
            return ChannelHealth(ok=False, detail=str(exc))
