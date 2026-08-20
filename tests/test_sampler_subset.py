"""Tests for problem subset extraction and filtering in Gaussian/Skew-Normal sampler."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.db.models import PracticeSession
from implegym.models.schemas import SamplerConfigSchema
from implegym.sampler.distribution import GaussianSampler


@pytest.mark.asyncio
async def test_sample_extracts_category_subset(db_session: AsyncSession) -> None:
    """Test that sampler extracts only problems belonging to the requested category subset."""
    sampler = GaussianSampler(db_session)

    # 1. Sample from 'Sample' category
    sample_cfg = SamplerConfigSchema(category="Sample", mean_difficulty=1.0, standard_deviation=1.0)
    for _ in range(5):
        prob = await sampler.sample_problem(sample_cfg)
        assert prob is not None
        assert prob.category == "Sample"
        assert prob.slug == "aplusb"

    # 2. Sample from 'Data Structure' category
    ds_cfg = SamplerConfigSchema(category="Data Structure", mean_difficulty=3.0, standard_deviation=1.5)
    for _ in range(10):
        prob = await sampler.sample_problem(ds_cfg)
        assert prob is not None
        assert prob.category == "Data Structure"


@pytest.mark.asyncio
async def test_sample_extracts_tag_subset(db_session: AsyncSession) -> None:
    """Test that sampler extracts only problems containing the specified tag."""
    sampler = GaussianSampler(db_session)

    # Sample with 'dsu' tag
    dsu_cfg = SamplerConfigSchema(tag="dsu", mean_difficulty=3.0, standard_deviation=1.0)
    for _ in range(5):
        prob = await sampler.sample_problem(dsu_cfg)
        assert prob is not None
        assert "dsu" in prob.tags
        assert prob.slug == "unionfind"


@pytest.mark.asyncio
async def test_sample_empty_subset_returns_none(db_session: AsyncSession) -> None:
    """Test that sampling from an impossible or non-existent subset returns None gracefully."""
    sampler = GaussianSampler(db_session)

    # 1. Non-existent category
    empty_cat_cfg = SamplerConfigSchema(category="NonExistentCategory12345")
    prob = await sampler.sample_problem(empty_cat_cfg)
    assert prob is None

    # 2. Non-existent tag
    empty_tag_cfg = SamplerConfigSchema(tag="non_existent_tag_xyz")
    prob = await sampler.sample_problem(empty_tag_cfg)
    assert prob is None


@pytest.mark.asyncio
async def test_sample_exclude_solved_subset(db_session: AsyncSession) -> None:
    """Test that exclude_solved correctly filters out already completed problems from the candidate subset."""
    sampler = GaussianSampler(db_session)

    # 1. Before solving, 'Sample' subset has 'aplusb'
    cfg_with_solved = SamplerConfigSchema(category="Sample", exclude_solved=False)
    prob_before = await sampler.sample_problem(cfg_with_solved)
    assert prob_before is not None
    assert prob_before.slug == "aplusb"

    # 2. Mark 'aplusb' as solved (status = 'ac')
    session_record = PracticeSession(
        problem_id=prob_before.id,
        status="ac",
        total_duration_seconds=120.0,
        submission_count=1,
    )
    db_session.add(session_record)
    await db_session.commit()

    # 3. Sample with exclude_solved=True for 'Sample' category
    # Since 'aplusb' is the only problem in 'Sample', the subset should now be empty
    cfg_exclude_solved = SamplerConfigSchema(category="Sample", exclude_solved=True)
    prob_after = await sampler.sample_problem(cfg_exclude_solved)
    assert prob_after is None

    # 4. Sampling from 'Data Structure' with exclude_solved=True should still yield unsolved problems
    ds_cfg = SamplerConfigSchema(category="Data Structure", exclude_solved=True)
    prob_ds = await sampler.sample_problem(ds_cfg)
    assert prob_ds is not None
    assert prob_ds.category == "Data Structure"
    assert prob_ds.slug != "aplusb"


@pytest.mark.asyncio
async def test_api_sampler_endpoint_subset_filtering(async_client: AsyncClient) -> None:
    """Test the POST /api/sampler/sample endpoint with subset extraction filters."""
    # 1. Valid category subset
    res = await async_client.post(
        "/api/sampler/sample",
        json={
            "category": "Data Structure",
            "mean_difficulty": 3.0,
            "standard_deviation": 1.0,
            "skewness": "balanced",
            "exclude_solved": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "Data Structure"
    assert 1 <= data["difficulty"] <= 10

    # 2. Impossible subset returns 404
    empty_res = await async_client.post(
        "/api/sampler/sample",
        json={
            "category": "ImpossibleCategoryXYZ",
            "mean_difficulty": 5.0,
        },
    )
    assert empty_res.status_code == 404
    assert "No problems found" in empty_res.json()["detail"]
