"""FastAPI control plane entrypoint.

Thin by design: REST + WebSocket gateway + channel webhooks + scheduler hooks.
The agent runtime lives in the worker process (app.runtime), never here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import settings
from app.logging import configure_logging, get_logger
from app.redis_client import close_redis, get_redis

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info("control_plane.starting", env=settings.app_env, llm_mode=settings.llm_mode)
    # Warm the Redis pool so the first request isn't slow.
    try:
        await get_redis().ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("redis.unreachable_at_boot", detail=str(exc))
    yield
    await close_redis()
    log.info("control_plane.stopped")


app = FastAPI(
    title="Yuno AI Agent Orchestration Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)


@app.get("/")
async def root() -> dict:
    return {"service": "yuno-orchestrator", "version": app.version}
