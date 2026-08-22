"""Tests for DatabaseSyncService bidirectional sync and migration."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from implegym.db.models import Base, Problem
from implegym.db.syncer import DatabaseSyncService


@pytest.mark.asyncio
async def test_database_sync_service(tmp_path: Path) -> None:
    """Test syncing data between source and target database file instances."""
    src_file = tmp_path / "src.db"
    tgt_file = tmp_path / "tgt.db"
    source_url = f"sqlite+aiosqlite:///{src_file}"
    target_url = f"sqlite+aiosqlite:///{tgt_file}"

    # Populate source DB
    src_eng = create_async_engine(source_url, connect_args={"check_same_thread": False})
    async with src_eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    src_factory = async_sessionmaker(src_eng, class_=AsyncSession)
    async with src_factory() as s:
        prob = Problem(
            slug="test_sync_prob",
            title="Sync Problem",
            category="Data Structures",
            difficulty=5,
            statement="Statement text",
            input_format="Input",
            output_format="Output",
            constraints="N <= 100",
            sample_cases=[{"input": "1 2", "output": "3"}],
            time_limit=2.0,
            memory_limit_mb=512,
            tags=["sync_test"],
            source="manual",
        )
        s.add(prob)
        await s.commit()

    await src_eng.dispose()

    # Perform Sync
    syncer = DatabaseSyncService(source_url=source_url, target_url=target_url)
    stats = await syncer.sync_data()

    assert stats["problems_synced"] == 1

    # Verify target DB has the synced problem
    tgt_eng = create_async_engine(target_url, connect_args={"check_same_thread": False})
    tgt_factory = async_sessionmaker(tgt_eng, class_=AsyncSession)
    async with tgt_factory() as s:
        res = await s.execute(select(Problem).where(Problem.slug == "test_sync_prob"))
        synced_prob = res.scalar_one_or_none()
        assert synced_prob is not None
        assert synced_prob.title == "Sync Problem"
        assert synced_prob.difficulty == 5

    await tgt_eng.dispose()
