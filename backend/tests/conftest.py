"""Test fixtures.

Tests run against a DEDICATED database (the configured db name + '_test') so the
live worker container — which uses the main db — never consumes test-enqueued runs
or test outbox rows. Each test starts from a truncated schema.

Requires a reachable Postgres (JSONB/ARRAY/UUID types).
"""

from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401 — register models on metadata
from app.db import session as dbsession
from app.db.session import Base


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    src = os.environ.get("DATABASE_URL", "postgresql+asyncpg://yuno:yuno@localhost:55432/yuno")
    url = make_url(src)
    # render_as_string(hide_password=False): str(url) masks the password as '***'.
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()


async def _ensure_database() -> None:
    """Drop + recreate the test database so its schema always matches the models
    (create_all with checkfirst won't add newly-introduced columns to an existing
    table, causing schema drift across runs)."""
    import asyncpg

    url = make_url(TEST_DATABASE_URL)
    admin_dsn = f"postgresql://{url.username}:{url.password}@{url.host}:{url.port}/postgres"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db():
    asyncio.run(_ensure_database())


@pytest.fixture(scope="session", autouse=True)
def _isolate_redis():
    # Point tests at a separate Redis db so enqueued test runs aren't consumed by
    # the live worker (which uses db 0).
    import re

    from app.config import settings

    settings.redis_url = re.sub(r"/\d+$", "/15", settings.redis_url) if re.search(r"/\d+$", settings.redis_url) else settings.redis_url + "/15"


@pytest.fixture(autouse=True)
def _reset_redis_pool():
    # The global Redis pool binds to the loop that created it; pytest-asyncio uses
    # a fresh loop per test, so reset around each test to avoid "loop is closed".
    import app.redis_client as rc

    rc._pool = None
    yield
    rc._pool = None


@pytest_asyncio.fixture
async def engine():
    # NullPool + a fresh engine per test avoids reusing asyncpg connections across
    # pytest's per-test event loops. The global SessionFactory (used by the
    # RunEngine under test) is rebound to this engine for the test's life.
    eng = create_async_engine(TEST_DATABASE_URL, future=True, poolclass=NullPool)
    dbsession.SessionFactory.configure(bind=eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
