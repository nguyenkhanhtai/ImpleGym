import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from implegym.config import settings  # noqa: E402
from implegym.db.models import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate support
target_metadata = Base.metadata


def get_db_url() -> str:
    """Retrieve database URL from settings with SQLite fallback."""
    url = settings.database_url
    if not url:
        url = "sqlite+aiosqlite:///data/implegym.db"
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active database connection."""
    is_sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async Engine and execute migrations with SQLite fallback."""
    db_url = get_db_url()
    candidates = [db_url]
    if "sqlite" not in db_url:
        candidates.append("sqlite+aiosqlite:///data/implegym.db")

    for candidate_url in candidates:
        section = config.get_section(config.config_ini_section, {})
        section["sqlalchemy.url"] = candidate_url

        connect_args = {}
        if "sqlite" in candidate_url:
            connect_args["check_same_thread"] = False
            Path("data").mkdir(parents=True, exist_ok=True)

        connectable = async_engine_from_config(
            section,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            connect_args=connect_args,
        )

        try:
            async with connectable.connect() as connection:
                await connection.run_sync(do_run_migrations)
            await connectable.dispose()
            break
        except Exception as e:
            await connectable.dispose()
            if candidate_url == candidates[-1]:
                raise e


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
