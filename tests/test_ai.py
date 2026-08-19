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
    assert any(s.category in ["Performance", "Memory Layout", "CP Idiom"] for s in review.suggestions)


@pytest.mark.asyncio
async def test_problem_generator_synthesis(db_session: AsyncSession) -> None:
    """Test composite problem generator synthesizes and indexes a problem into database."""
    generator = ProblemGeneratorService(db_session)
    req = GenerateProblemRequest(
        topic_1="Fenwick Tree",
        topic_2="Range Minimum Query",
        target_difficulty=7,
    )
    new_prob = await generator.generate_problem(req)
    assert new_prob.id is not None
    assert "ai_" in new_prob.slug
    assert new_prob.difficulty == 7
    assert new_prob.source == "gpt_generated"
    assert len(new_prob.sample_cases) > 0
