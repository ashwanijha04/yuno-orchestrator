"""Test fixtures. Each test runs inside a transaction that is rolled back, so
the database is left untouched. Repos only flush (never commit), which keeps the
outer transaction intact for rollback.

Requires a reachable Postgres (JSONB/ARRAY/UUID types). Point TEST_DATABASE_URL
at it; defaults to the local compose Postgres on host port 55432.
"""

from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401 — register models on metadata
from app.db import session as dbsession
from app.db.session import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://yuno:yuno@localhost:55432/yuno"
    ),
)


@pytest_asyncio.fixture
async def engine():
    # NullPool + a fresh engine per test avoids reusing asyncpg connections
    # across pytest's per-test event loops. The global SessionFactory (used by
    # the RunEngine under test) is rebound to this engine for the test's life.
    eng = create_async_engine(TEST_DATABASE_URL, future=True, poolclass=NullPool)
    dbsession.SessionFactory.configure(bind=eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # idempotent (checkfirst)
        # Clean slate every test: runtime tests commit real rows, so isolate by
        # truncating up front rather than relying on rollback alone.
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
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
