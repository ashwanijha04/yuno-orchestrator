"""Test fixtures. Each test runs inside a transaction that is rolled back, so
the database is left untouched. Repos only flush (never commit), which keeps the
outer transaction intact for rollback.

Requires a reachable Postgres (JSONB/ARRAY/UUID types). Point TEST_DATABASE_URL
at it; defaults to the local compose Postgres on host port 55432.
"""

from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import models  # noqa: F401 — register models on metadata
from app.db.session import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://yuno:yuno@localhost:55432/yuno"
    ),
)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # idempotent (checkfirst)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    conn = await engine.connect()
    trans = await conn.begin()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False)
    sess = factory()
    try:
        yield sess
    finally:
        await sess.close()
        await trans.rollback()
        await conn.close()
