"""Tests for session lifecycle, stopwatch tracking, and AC timer halt."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.models.schemas import SubmissionCreateRequest
from implegym.problems.catalog import ProblemCatalogService
from implegym.session.tracker import SessionTracker


@pytest.mark.asyncio
async def test_session_lifecycle_and_stopwatch_ac(db_session: AsyncSession) -> None:
    """Test session start, intermediate WA submissions, and stopwatch halting on AC."""
    catalog = ProblemCatalogService(db_session)
    prob = await catalog.get_by_slug("aplusb")
    assert prob is not None

    tracker = SessionTracker(db_session)
    session = await tracker.start_session(problem_id=prob.id, is_manual_selection=True)
    assert session.status == "active"
    assert session.started_at is not None
    assert session.finished_at is None
    assert session.submission_count == 0

    # 1. Submit Wrong Answer
    wa_req = SubmissionCreateRequest(
        session_id=session.id,
        problem_slug="aplusb",
        code="""
        #include <iostream>
        int main() {
            long long a, b;
            std::cin >> a >> b;
            std::cout << (a - b) << "\\n";
            return 0;
        }
        """,
        compiler_profile="g++ (C++20)",
    )
    wa_sub, updated_sess = await tracker.submit_code(wa_req)
    assert wa_sub.verdict == "WA"
    assert updated_sess is not None
    assert updated_sess.status == "active"
    assert updated_sess.submission_count == 1
    assert updated_sess.finished_at is None

    # 2. Submit Accepted solution
    ac_req = SubmissionCreateRequest(
        session_id=session.id,
        problem_slug="aplusb",
        code="""
        #include <iostream>
        int main() {
            long long a, b;
            std::cin >> a >> b;
            std::cout << (a + b) << "\\n";
            return 0;
        }
        """,
        compiler_profile="g++ (C++20)",
    )
    ac_sub, final_sess = await tracker.submit_code(ac_req)
    assert ac_sub.verdict == "AC"
    assert final_sess is not None
    assert final_sess.status == "ac"
    assert final_sess.finished_at is not None
    assert final_sess.total_duration_seconds is not None
    assert final_sess.total_duration_seconds >= 0.0
    assert final_sess.submission_count == 2
