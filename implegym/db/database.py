"""Database engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from implegym.config import settings
from implegym.db.models import Base

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """Retrieve or create the global async database engine."""
    global _engine
    if _engine is None or db_url is not None:
        target_url = db_url or settings.database_url
        # SQLite async requires special connect args for threading
        connect_args = {}
        if "sqlite" in target_url:
            connect_args = {"check_same_thread": False}
        
        _engine = create_async_engine(
            target_url,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Retrieve or create the async session factory."""
    global _session_factory
    if _session_factory is None or engine is not None:
        eng = engine or get_engine()
        _session_factory = async_sessionmaker(
            bind=eng,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Initialize database tables."""
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator for FastAPI routes."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for standalone database operations."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
