"""Health endpoints. The UI surfaces these (db/redis/channels status badges)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "llm_mode": settings.llm_mode}


@router.get("/health/db")
async def health_db() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 — health endpoint reports, never raises
        return {"status": "error", "detail": str(exc)}


@router.get("/health/redis")
async def health_redis() -> dict:
    try:
        pong = await get_redis().ping()
        return {"status": "ok" if pong else "error"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


@router.get("/health/channels")
async def health_channels() -> dict:
    # Channel adapters register here once Phase 6 lands; until then report config presence.
    return {
        "status": "ok",
        "telegram": {
            "configured": settings.telegram_bot_token is not None,
            "transport": settings.telegram_transport,
        },
    }
