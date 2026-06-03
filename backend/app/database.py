from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

log = logging.getLogger(__name__)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url.replace("postgresql://", "postgresql+asyncpg://")


def _make_engine():
    return create_async_engine(_database_url(), pool_pre_ping=True)


# Lazily initialized so a missing DATABASE_URL doesn't crash at import time
_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


class Base(DeclarativeBase):
    pass


async def get_db():
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    try:
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Database tables initialised.")
    except Exception as exc:
        log.error("Database init failed: %s", exc)
        raise
