"""Tests for YosupoSyncer module."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.problems.catalog import ProblemCatalogService
from implegym.problems.yosupo_syncer import YosupoSyncer


@pytest.mark.asyncio
async def test_yosupo_syncer_difficulty_calculation(db_session: AsyncSession) -> None:
    """Test difficulty assignment heuristics for known and category baselines."""
    syncer = YosupoSyncer(db_session)
    from pathlib import Path

    tmp_path = Path("dummy_dir")

    # Known problems
    assert syncer._calculate_difficulty("aplusb", "sample", tmp_path) == 1
    assert (
        syncer._calculate_difficulty("dynamic_tree_subtree_add_subtree_sum", "tree", tmp_path) == 10
    )
    assert syncer._calculate_difficulty("point_add_range_sum", "datastructure", tmp_path) == 4

    # Baseline heuristics
    assert syncer._calculate_difficulty("unknown_matrix_problem", "matrix", tmp_path) == 6
    assert syncer._calculate_difficulty("unknown_geom_problem", "geometry", tmp_path) == 7


@pytest.mark.asyncio
async def test_yosupo_syncer_preserves_custom_difficulty(db_session: AsyncSession) -> None:
    """Test that syncing problems preserves user-customized difficulties."""
    catalog = ProblemCatalogService(db_session)
    # 1. Update difficulty of a problem
    updated = await catalog.update_problem("aplusb", {"difficulty": 8})
    assert updated is not None
    assert updated.difficulty == 8
    assert updated.is_difficulty_customized is True

    # 2. Run sync_problem for aplusb
    syncer = YosupoSyncer(db_session)
    await syncer.sync_problem("aplusb")

    # 3. Verify difficulty remains 8 (preserved)
    refreshed = await catalog.get_by_slug("aplusb")
    assert refreshed is not None
    assert refreshed.difficulty == 8
    assert refreshed.is_difficulty_customized is True
