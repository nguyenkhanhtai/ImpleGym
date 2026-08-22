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


@pytest.mark.asyncio
async def test_session_manual_stop(db_session: AsyncSession) -> None:
    """Test manually stopping/pausing an active workout session."""
    catalog = ProblemCatalogService(db_session)
    prob = await catalog.get_by_slug("aplusb")
    assert prob is not None

    tracker = SessionTracker(db_session)
    session = await tracker.start_session(problem_id=prob.id, is_manual_selection=True)
    assert session.status == "active"

    # Stop session manually
    stopped = await tracker.stop_session(session.id)
    assert stopped is not None
    assert stopped.status == "stopped"
    assert stopped.finished_at is not None
    assert stopped.total_duration_seconds is not None
    assert 0.0 <= stopped.total_duration_seconds < 5.0
    # Verify timezone offset awareness (UTC)
    assert stopped.started_at.tzinfo is not None
    assert stopped.finished_at.tzinfo is not None
    delta = (stopped.finished_at - stopped.started_at).total_seconds()
    assert 0.0 <= delta < 5.0


@pytest.mark.asyncio
async def test_contest_multi_problem_lifecycle_and_switching(db_session: AsyncSession) -> None:
    """Test full multi-problem contest session: custom name, problem switching, per-problem AC, and contest AC."""
    catalog = ProblemCatalogService(db_session)
    prob1 = await catalog.get_by_slug("aplusb")
    prob2 = await catalog.get_by_slug("unionfind")
    assert prob1 is not None and prob2 is not None

    tracker = SessionTracker(db_session)
    contest_name = "Nightly Speedrun Contest"
    sess = await tracker.start_session(
        problem_ids=[prob1.id, prob2.id],
        name=contest_name,
        is_manual_selection=True,
    )

    assert sess.name == contest_name
    assert sess.num_problems == 2
    assert sess.solved_count == 0
    assert sess.status == "active"
    assert len(sess.problems) == 2
    assert sess.problem_id == prob1.id

    # 1. Switch to Problem 2
    switched = await tracker.switch_session_problem(
        session_id=sess.id,
        problem_id=prob2.id,
        problem_index=1,
    )
    assert switched.problem_id == prob2.id
    assert switched.current_problem_index == 1

    # 2. Submit AC solution for Problem 1
    ac_prob1_req = SubmissionCreateRequest(
        session_id=sess.id,
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
    sub1, sess_after_prob1 = await tracker.submit_code(ac_prob1_req)
    assert sub1.verdict == "AC"
    assert sess_after_prob1 is not None
    assert (
        sess_after_prob1.status == "active"
    )  # Remains active because Problem 2 is not yet solved!
    assert sess_after_prob1.solved_count == 1
    assert sess_after_prob1.problem_statuses.get(str(prob1.id)) == "ac"

    # 3. Submit AC solution for Problem 2 (Unionfind)
    ac_prob2_req = SubmissionCreateRequest(
        session_id=sess.id,
        problem_slug="unionfind",
        code="""
        #include <iostream>
        #include <vector>
        using namespace std;
        struct DSU {
            vector<int> p;
            DSU(int n) : p(n, -1) {}
            int leader(int a) {
                return p[a] < 0 ? a : p[a] = leader(p[a]);
            }
            bool same(int a, int b) { return leader(a) == leader(b); }
            bool merge(int a, int b) {
                int x = leader(a), y = leader(b);
                if (x == y) return false;
                if (-p[x] < -p[y]) swap(x, y);
                p[x] += p[y];
                p[y] = x;
                return true;
            }
        };
        int main() {
            ios_base::sync_with_stdio(false);
            cin.tie(NULL);
            int n, q;
            if (!(cin >> n >> q)) return 0;
            DSU dsu(n);
            while (q--) {
                int t, u, v;
                cin >> t >> u >> v;
                if (t == 0) dsu.merge(u, v);
                else cout << (dsu.same(u, v) ? 1 : 0) << "\\n";
            }
            return 0;
        }
        """,
        compiler_profile="g++ (C++20)",
    )
    sub2, sess_final = await tracker.submit_code(ac_prob2_req)
    assert sub2.verdict == "AC"
    assert sess_final is not None
    assert sess_final.status == "ac"  # All contest problems solved!
    assert sess_final.solved_count == 2
    assert sess_final.finished_at is not None
    assert sess_final.total_duration_seconds is not None
