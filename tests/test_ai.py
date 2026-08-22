"""Tests for AI code refiner and composite problem synthesizer."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from implegym.ai.generator import ProblemGeneratorService
from implegym.ai.refiner import CodeRefinerService
from implegym.models.schemas import GenerateProblemRequest, SubmissionCreateRequest
from implegym.session.tracker import SessionTracker


@pytest.mark.asyncio
async def test_code_refiner_fallback_structure(db_session: AsyncSession) -> None:
    """Test AI code refiner returns structured feedback and suggestions."""
    tracker = SessionTracker(db_session)
    req = SubmissionCreateRequest(
        problem_slug="aplusb",
        code="#include <iostream>\nint main() { return 0; }",
        compiler_profile="g++ (C++20)",
    )
    sub, _ = await tracker.submit_code(req)

    refiner = CodeRefinerService(db_session)
    review = await refiner.refine_submission(sub.id)
    assert review.submission_id == sub.id
    assert len(review.feedback_markdown) > 0
    assert len(review.suggestions) > 0
    assert any(
        s.category in ["Performance", "Memory Layout", "CP Idiom"] for s in review.suggestions
    )


@pytest.mark.asyncio
async def test_problem_generator_synthesis_and_self_test(db_session: AsyncSession) -> None:
    """Test composite problem generator compiles generator, creates tests, and verifies solution."""
    generator = ProblemGeneratorService(db_session)
    req = GenerateProblemRequest(
        topic_1="Fenwick Tree",
        topic_2="Range Sum",
        target_difficulty=4,
    )
    new_prob = await generator.generate_problem(req)
    assert new_prob.id is not None
    assert "ai_" in new_prob.slug
    assert new_prob.difficulty == 4
    assert new_prob.source == "gpt_generated"
    # Verify that generator produced multiple test cases beyond initial sample
    assert len(new_prob.sample_cases) >= 2
    # Verify self_test tag is present
    assert any("self_test_ac" in tag for tag in new_prob.tags)
