"""Connect a Telegram bot to an agent (default: Jarvis) so it's reachable on
Telegram — locally, via long-polling (no public tunnel needed).

Usage:
    python -m scripts.connect_telegram <BOT_TOKEN> [AgentName]

What it does:
  1. validates the bot token (getMe),
  2. registers a Telegram channel with that token (reusing one if it already exists),
  3. binds external_id="*" -> the agent, so ANY chat with the bot reaches it.

The worker polls active Telegram channels automatically (TELEGRAM_TRANSPORT=polling,
the default), so once this runs you can just message the bot.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from app.db.repositories import AgentRepository, ChannelRepository
from app.db.session import SessionFactory
from app.logging import configure_logging, get_logger

log = get_logger("connect_telegram")


async def main() -> None:
    configure_logging()
    if len(sys.argv) < 2:
        print("usage: python -m scripts.connect_telegram <BOT_TOKEN> [AgentName]")
        return
    token = sys.argv[1].strip()
    agent_name = sys.argv[2] if len(sys.argv) > 2 else "Jarvis"

    # 1. Validate the token.
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        data = resp.json() if resp.status_code == 200 else {}
    if not data.get("ok"):
        print("❌ Invalid bot token — get one from @BotFather and try again.")
        return
    bot = data["result"].get("username", "bot")

    async with SessionFactory() as s:
        agent = await AgentRepository(s).get_by_name(agent_name)
        if agent is None:
            print(f"❌ Agent {agent_name!r} not found. Run `python -m scripts.seed` first.")
            return
        chans = ChannelRepository(s)
        existing = [
            c for c in await chans.list()
            if c.type == "telegram" and (c.config or {}).get("bot_token") == token
        ]
        channel = existing[0] if existing else await chans.create(
            type="telegram", name=f"Telegram · @{bot}", config={"bot_token": token}
        )
        binds = await chans.bindings_for_channel(channel.id)
        if not any(b.external_id == "*" and b.agent_id == agent.id for b in binds):
            await chans.add_binding(channel.id, external_id="*", agent_id=agent.id)
        await s.commit()

    print(f"✅ Connected @{bot} → {agent_name}.")
    print("   Open Telegram, message your bot, and it will reply. The worker is polling.")


if __name__ == "__main__":
    asyncio.run(main())
