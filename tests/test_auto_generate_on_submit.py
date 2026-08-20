"""Test verifying auto testcase generation and database caching on submit."""

import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from implegym.db.models import Problem, PracticeSession
from implegym.session.tracker import SessionTracker
from implegym.models.schemas import SubmissionCreateRequest


@pytest.mark.asyncio
async def test_auto_generate_and_cache_on_submit(db_session: AsyncSession) -> None:
    """Verify testcases are generated automatically upon submit and cached in DB for reuse."""
    prob_dir = Path("data") / "yosupo_repo" / "data_structure" / "static_range_sum"
    if not prob_dir.exists():
        pytest.skip("yosupo_repo not available")

    # 1. Setup problem with only 1 sample case in DB
    sample_only = [{"input": "5 1\n1 2 3 4 5\n0 5\n", "output": "15\n"}]
    problem = Problem(
        slug="static_range_sum",
        title="Static Range Sum",
        category="Data Structure",
        difficulty=2,
        statement="Range sum test",
        sample_cases=sample_only,
        time_limit=5.0,
        memory_limit_mb=1024,
        source="yosupo_official",
    )
    db_session.add(problem)
    await db_session.commit()
    await db_session.refresh(problem)

    assert len(problem.sample_cases) == 1

    # 2. Submit fast correct solution
    tracker = SessionTracker(db_session)
    fast_cpp = r"""
#include <iostream>
#include <vector>

using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    int n, q;
    if (!(cin >> n >> q)) return 0;

    vector<long long> pref(n + 1, 0);
    for (int i = 0; i < n; ++i) {
        long long a;
        cin >> a;
        pref[i + 1] = pref[i] + a;
    }

    for (int i = 0; i < q; ++i) {
        int l, r;
        cin >> l >> r;
        cout << (pref[r] - pref[l]) << "\n";
    }
    return 0;
}
"""

    sub_req = SubmissionCreateRequest(
        problem_slug="static_range_sum",
        code=fast_cpp,
        language="cpp",
        compiler_profile="g++ (C++20)",
    )

    sub_res, _ = await tracker.submit_code(sub_req)

    # 3. Verify evaluation ran against generated testcases and got AC
    assert sub_res.verdict == "AC"
    assert len(sub_res.test_results) > 1

    # 4. Verify testcases are now cached in DB
    await db_session.refresh(problem)
    assert len(problem.sample_cases) > 1
    assert any(tc.get("name", "").startswith("random") for tc in problem.sample_cases)

    # 5. Subsequent submission reuses cached testcases without regenerating
    sub_res2, _ = await tracker.submit_code(sub_req)
    assert sub_res2.verdict == "AC"
    assert len(sub_res2.test_results) == len(problem.sample_cases)
