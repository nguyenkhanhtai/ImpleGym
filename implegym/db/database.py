"""Database engine and session management with resilient PostgreSQL and SQLite fallback."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from implegym.config import settings
from implegym.db.models import Base

logger = logging.getLogger("implegym.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Retrieve or create the global async database engine."""
    global _engine
    if _engine is None or db_url is not None:
        target_url = db_url or settings.database_url
        connect_args = {}
        if "sqlite" in target_url:
            connect_args = {"check_same_thread": False}
            if ":///" in target_url and not target_url.endswith(":memory:"):
                db_rel_path = target_url.split(":///")[-1]
                path_obj = Path(db_rel_path)
                if path_obj.parent:
                    path_obj.parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            target_url,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
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


def _auto_migrate_tables(sync_conn: Any) -> None:
    """Ensure newly added columns exist in existing database tables."""
    dialect_name = sync_conn.dialect.name
    if dialect_name == "sqlite":
        # Check practice_sessions table info
        result = sync_conn.exec_driver_sql("PRAGMA table_info(practice_sessions)").fetchall()
        existing_cols = {row[1] for row in result}

        if existing_cols:
            if "name" not in existing_cols:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE practice_sessions ADD COLUMN name VARCHAR(256) DEFAULT '' NOT NULL"
                )
            if "problem_ids" not in existing_cols:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE practice_sessions ADD COLUMN problem_ids JSON DEFAULT '[]' NOT NULL"
                )
            if "current_problem_index" not in existing_cols:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE practice_sessions ADD COLUMN current_problem_index INTEGER DEFAULT 0 NOT NULL"
                )
            if "problem_statuses" not in existing_cols:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE practice_sessions ADD COLUMN problem_statuses JSON DEFAULT '{}' NOT NULL"
                )

            # Backfill problem_ids with single problem_id for older sessions
            try:
                sync_conn.exec_driver_sql(
                    "UPDATE practice_sessions SET problem_ids = json_array(problem_id) WHERE problem_ids IS NULL OR problem_ids = '[]'"
                )
            except Exception:
                pass

        # Check problems table info
        prob_result = sync_conn.exec_driver_sql("PRAGMA table_info(problems)").fetchall()
        existing_prob_cols = {row[1] for row in prob_result}
        if existing_prob_cols and "is_difficulty_customized" not in existing_prob_cols:
            sync_conn.exec_driver_sql(
                "ALTER TABLE problems ADD COLUMN is_difficulty_customized BOOLEAN DEFAULT 0 NOT NULL"
            )
    elif dialect_name == "postgresql":
        try:
            sync_conn.exec_driver_sql(
                "ALTER TABLE practice_sessions ADD COLUMN IF NOT EXISTS name VARCHAR(256) DEFAULT '' NOT NULL"
            )
            sync_conn.exec_driver_sql(
                "ALTER TABLE practice_sessions ADD COLUMN IF NOT EXISTS problem_ids JSONB DEFAULT '[]'::jsonb NOT NULL"
            )
            sync_conn.exec_driver_sql(
                "ALTER TABLE practice_sessions ADD COLUMN IF NOT EXISTS current_problem_index INTEGER DEFAULT 0 NOT NULL"
            )
            sync_conn.exec_driver_sql(
                "ALTER TABLE practice_sessions ADD COLUMN IF NOT EXISTS problem_statuses JSONB DEFAULT '{}'::jsonb NOT NULL"
            )
            sync_conn.exec_driver_sql(
                "ALTER TABLE problems ADD COLUMN IF NOT EXISTS is_difficulty_customized BOOLEAN DEFAULT FALSE NOT NULL"
            )
        except Exception:
            pass


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Initialize database tables with automatic fallback to SQLite if PostgreSQL server is not running."""
    global _engine, _session_factory
    eng = engine or get_engine()

    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_auto_migrate_tables)
    except (OSError, ConnectionRefusedError, Exception) as ex:
        # If target was Postgres and it failed to connect (e.g. port 5432 down)
        if "postgresql" in str(eng.url):
            logger.warning(
                "⚠️ PostgreSQL is not reachable at %s (%s). Falling back to local SQLite at data/implegym.db",
                eng.url,
                ex,
            )
            print(
                "\n[ImpleGym Notice] PostgreSQL is not running on localhost:5432. "
                "Automatically switching to local SQLite storage (data/implegym.db) so you can use the app immediately.\n"
                "(To use PostgreSQL, start your container with `docker-compose up -d postgres`)\n"
            )
            # Create data directory if not present
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            fallback_url = "sqlite+aiosqlite:///data/implegym.db"

            _engine = create_async_engine(
                fallback_url,
                echo=False,
                future=True,
                connect_args={"check_same_thread": False},
            )
            _session_factory = async_sessionmaker(
                bind=_engine,
                autoflush=False,
                expire_on_commit=False,
                class_=AsyncSession,
            )
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.run_sync(_auto_migrate_tables)
        else:
            raise ex


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
