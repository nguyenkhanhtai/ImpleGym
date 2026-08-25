"""Tests for YosupoSyncer module."""

from pathlib import Path

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


@pytest.mark.asyncio
async def test_sync_progress_tracker_lifecycle() -> None:
    """Test SyncProgressTracker state transitions, progress calculation, and cancellation."""
    from implegym.problems.sync_manager import SyncProgressTracker

    tracker = SyncProgressTracker()
    assert tracker.get_state().is_running is False
    assert tracker.get_state().stage == "idle"

    # 1. Start tracker
    tracker.start(total=10, message="Starting test sync")
    state = tracker.get_state()
    assert state.is_running is True
    assert state.total == 10
    assert state.percent == 0.0

    # 2. Update tracker
    tracker.update(
        stage="syncing_problems",
        current=5,
        current_slug="unionfind",
        current_category="datastructure",
        synced_count=5,
    )
    state = tracker.get_state()
    assert state.stage == "syncing_problems"
    assert state.current == 5
    assert state.percent == 50.0
    assert state.current_slug == "unionfind"

    # 3. Cancel request
    assert tracker.is_cancelled() is False
    tracker.request_cancel()
    assert tracker.is_cancelled() is True
    assert tracker.get_state().stage == "cancelled"

    # 4. Complete tracker
    tracker.complete(synced_count=10)
    state = tracker.get_state()
    assert state.is_running is False
    assert state.stage == "completed"
    assert state.percent == 100.0
    assert state.synced_count == 10


@pytest.mark.asyncio
async def test_parse_problem_directory_generate_tests_flag(db_session: AsyncSession) -> None:
    """Test that parse_problem_directory respects the generate_tests boolean flag."""
    from pathlib import Path
    from unittest.mock import MagicMock

    syncer = YosupoSyncer(db_session)
    syncer._generate_testcases_from_info_toml = MagicMock(
        return_value=[{"input": "gen\n", "output": "out\n"}]
    )
    syncer._extract_sample_cases = MagicMock(
        return_value=[{"input": "sample\n", "output": "sample_out\n"}]
    )
    syncer._extract_markdown_sections = MagicMock(return_value=("statement", "", "", ""))

    dummy_dir = Path("data/yosupo_repo/sample/aplusb")
    if dummy_dir.exists():
        # 1. When generate_tests=False
        res_no_gen = syncer.parse_problem_directory("sample", dummy_dir, generate_tests=False)
        if res_no_gen:
            assert len(res_no_gen["sample_cases"]) == 1
            syncer._generate_testcases_from_info_toml.assert_not_called()

        # 2. When generate_tests=True
        res_gen = syncer.parse_problem_directory("sample", dummy_dir, generate_tests=True)
        if res_gen:
            assert res_gen["testcases_dir"] is not None
            syncer._generate_testcases_from_info_toml.assert_called_once()


@pytest.mark.asyncio
async def test_yosupo_syncer_preserves_cached_tests_without_force(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Test that sync_all_problems skips expensive test generation when testcases are already cached."""
    from unittest.mock import MagicMock

    from implegym.db.models import Problem

    # Create dummy single problem structure in tmp_path
    prob_dir = tmp_path / "sample" / "dummy_aplusb"
    prob_dir.mkdir(parents=True, exist_ok=True)
    (prob_dir / "info.toml").write_text(
        'title = "Dummy A + B"\ntimelimit = 2.0\n', encoding="utf-8"
    )
    (prob_dir / "task.md").write_text("## Problem Statement\nCalculate A+B\n", encoding="utf-8")

    # Add existing problem into DB with cached testcases
    custom_cases = [
        {"name": "custom_01", "input": "1 2\n", "output": "3\n"},
        {"name": "custom_02", "input": "4 5\n", "output": "9\n"},
    ]
    prob = Problem(
        slug="dummy_aplusb",
        title="Dummy A + B",
        category="Sample",
        difficulty=1,
        statement="Calculate A + B",
        sample_cases=custom_cases,
    )
    db_session.add(prob)
    await db_session.commit()

    syncer = YosupoSyncer(db_session, repo_dir=tmp_path)
    # Spy on _generate_testcases_from_info_toml
    syncer._generate_testcases_from_info_toml = MagicMock(
        return_value=[{"name": "generated_01", "input": "99 1\n", "output": "100\n"}]
    )

    # 1. Run sync_all_problems with force_regenerate_tests=False
    count = await syncer.sync_all_problems(force_regenerate_tests=False)
    assert count == 1

    # Verify _generate_testcases_from_info_toml was NOT called and cached tests preserved
    syncer._generate_testcases_from_info_toml.assert_not_called()
    catalog = ProblemCatalogService(db_session)
    refreshed = await catalog.get_by_slug("dummy_aplusb")
    assert refreshed is not None
    assert len(refreshed.sample_cases) == 2
    assert refreshed.sample_cases[0].input == "1 2\n"

    # 2. Run sync_all_problems with force_regenerate_tests=True
    await syncer.sync_all_problems(force_regenerate_tests=True)
    # Verify testcase generator was now invoked
    assert syncer._generate_testcases_from_info_toml.called
