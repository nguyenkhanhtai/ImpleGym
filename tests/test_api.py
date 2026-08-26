"""Tests for FastAPI REST endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient) -> None:
    """Test health endpoint."""
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "app": "ImpleGym"}


@pytest.mark.asyncio
async def test_compilers_endpoint(async_client: AsyncClient) -> None:
    """Test listing available compiler profiles."""
    res = await async_client.get("/api/compilers")
    assert res.status_code == 200
    compilers = res.json()
    assert len(compilers) > 0
    assert any("g++" in c["name"] for c in compilers)


@pytest.mark.asyncio
async def test_list_problems_endpoint(async_client: AsyncClient) -> None:
    """Test listing problems with pagination, category and difficulty filters."""
    res = await async_client.get(
        "/api/problems?min_difficulty=1&max_difficulty=10&page=1&page_size=2"
    )
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] > 0
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2
    assert data["total_pages"] >= 1


@pytest.mark.asyncio
async def test_start_session_and_submit_flow(async_client: AsyncClient) -> None:
    """Test starting session, submitting code, and fetching active session."""
    # 1. Start session
    start_res = await async_client.post("/api/session/start", json={"problem_slug": "aplusb"})
    assert start_res.status_code == 200
    session_data = start_res.json()
    assert session_data["status"] == "active"
    session_id = session_data["id"]

    # 2. Check active session
    active_res = await async_client.get("/api/session/active")
    assert active_res.status_code == 200
    assert active_res.json()["id"] == session_id

    # 3. Submit solution
    sub_res = await async_client.post(
        "/api/session/submit",
        json={
            "session_id": session_id,
            "problem_slug": "aplusb",
            "code": "#include <iostream>\nint main(){long long a,b; std::cin>>a>>b; std::cout<<(a+b)<<'\\n'; return 0;}",
            "compiler_profile": "g++ (C++20)",
            "compiler_flags": "-O3",
        },
    )
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["submission"]["verdict"] == "AC"
    assert sub_data["session"]["status"] == "ac"
    assert sub_data["session"]["finished_at"] is not None
    assert sub_data["session"]["total_duration_seconds"] is not None
    assert sub_data["session"]["total_duration_seconds"] >= 0.0

    # Verify active session is now closed (None)
    active_check = await async_client.get("/api/session/active")
    assert active_check.status_code == 200
    assert active_check.json() is None

    # 4. Request AI refinement
    submission_id = sub_data["submission"]["id"]
    refine_res = await async_client.post(f"/api/submissions/{submission_id}/refine")
    assert refine_res.status_code == 200
    review_data = refine_res.json()
    assert review_data["submission_id"] == submission_id
    assert len(review_data["suggestions"]) > 0


@pytest.mark.asyncio
async def test_update_problem_difficulty(async_client: AsyncClient) -> None:
    """Test manually updating problem difficulty and verifying is_difficulty_customized flag."""
    # 1. Update difficulty of aplusb from 1 to 3
    patch_res = await async_client.patch(
        "/api/problems/aplusb",
        json={"difficulty": 3},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["slug"] == "aplusb"
    assert data["difficulty"] == 3
    assert data["is_difficulty_customized"] is True

    # 2. Fetch problem again to verify persistence
    get_res = await async_client.get("/api/problems/aplusb")
    assert get_res.status_code == 200
    assert get_res.json()["difficulty"] == 3
    assert get_res.json()["is_difficulty_customized"] is True


@pytest.mark.asyncio
async def test_delete_submission_record(async_client: AsyncClient) -> None:
    """Test adding a submission and then deleting that exact record."""
    # 1. Start a session
    start_res = await async_client.post("/api/session/start", json={"problem_slug": "aplusb"})
    assert start_res.status_code == 200
    sess_id = start_res.json()["id"]

    # 2. Submit code to create a submission record
    sub_res = await async_client.post(
        "/api/session/submit",
        json={
            "session_id": sess_id,
            "problem_slug": "aplusb",
            "code": "#include <iostream>\nint main(){long long a,b; std::cin>>a>>b; std::cout<<(a+b)<<'\\n'; return 0;}",
            "compiler_profile": "g++ (C++20)",
            "compiler_flags": "-O3",
        },
    )
    assert sub_res.status_code == 200
    submission_id = sub_res.json()["submission"]["id"]

    # 3. Verify submission exists
    get_res = await async_client.get(f"/api/submissions/{submission_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == submission_id

    # 4. Delete the exact submission record
    del_res = await async_client.delete(f"/api/submissions/{submission_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"status": "deleted", "id": submission_id}

    # 5. Verify submission no longer exists (404)
    get_after_del = await async_client.get(f"/api/submissions/{submission_id}")
    assert get_after_del.status_code == 404

    # 6. Deleting again returns 404
    del_again = await async_client.delete(f"/api/submissions/{submission_id}")
    assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_problem_success_target_time_benchmark(async_client: AsyncClient) -> None:
    """Test that a problem solved under (difficulty * 5) minutes is marked as is_successful."""
    # 1. Start a session for aplusb (diff 1 -> target 300s / 5m)
    start_res = await async_client.post("/api/session/start", json={"problem_slug": "aplusb"})
    assert start_res.status_code == 200
    sess_data = start_res.json()
    assert (
        sess_data["problem"]["target_time_seconds"] == sess_data["problem"]["difficulty"] * 5 * 60.0
    )

    # 2. Submit solution
    sub_res = await async_client.post(
        "/api/session/submit",
        json={
            "session_id": sess_data["id"],
            "problem_slug": "aplusb",
            "code": "#include <iostream>\nint main(){long long a,b; std::cin>>a>>b; std::cout<<(a+b)<<'\\n'; return 0;}",
            "compiler_profile": "g++ (C++20)",
            "compiler_flags": "-O3",
        },
    )
    assert sub_res.status_code == 200
    res_data = sub_res.json()
    assert res_data["session"]["status"] == "ac"
    assert res_data["session"]["is_successful"] is True
    assert (
        res_data["session"]["total_duration_seconds"] <= res_data["session"]["target_time_seconds"]
    )

    # 3. Check problem catalog reflects is_successful = True
    prob_res = await async_client.get("/api/problems/aplusb")
    assert prob_res.status_code == 200
    prob_info = prob_res.json()
    assert prob_info["is_solved"] is True
    assert prob_info["is_successful"] is True
    assert prob_info["target_time_seconds"] == prob_info["difficulty"] * 300.0


@pytest.mark.asyncio
async def test_multi_page_routes_serve_html(async_client: AsyncClient) -> None:
    """Test that all dedicated frontend page routes serve valid HTML."""
    routes = ["/", "/problems", "/explorer", "/gym", "/history", "/forge"]
    for route in routes:
        res = await async_client.get(route)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in res.text
        assert "ImpleGym" in res.text


@pytest.mark.asyncio
async def test_submission_and_session_history_endpoint(async_client: AsyncClient) -> None:
    """Test creating multiple submissions in a session and querying session/submission history."""
    # 1. Start a session
    start_res = await async_client.post("/api/session/start", json={"problem_slug": "aplusb"})
    assert start_res.status_code == 200
    sess_id = start_res.json()["id"]

    # 2. First submission: Wrong Answer
    wa_res = await async_client.post(
        "/api/session/submit",
        json={
            "session_id": sess_id,
            "problem_slug": "aplusb",
            "code": "#include <iostream>\nint main(){long long a,b; std::cin>>a>>b; std::cout<<(a-b)<<'\\n'; return 0;}",
            "compiler_profile": "g++ (C++20)",
            "compiler_flags": "-O3",
        },
    )
    assert wa_res.status_code == 200
    assert wa_res.json()["submission"]["verdict"] == "WA"

    # 3. Second submission: Accepted
    ac_res = await async_client.post(
        "/api/session/submit",
        json={
            "session_id": sess_id,
            "problem_slug": "aplusb",
            "code": "#include <iostream>\nint main(){long long a,b; std::cin>>a>>b; std::cout<<(a+b)<<'\\n'; return 0;}",
            "compiler_profile": "g++ (C++20)",
            "compiler_flags": "-O3",
        },
    )
    assert ac_res.status_code == 200
    assert ac_res.json()["submission"]["verdict"] == "AC"

    # 4. Fetch session history list
    history_res = await async_client.get("/api/history/sessions")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) > 0

    # Locate the target session
    matching_sessions = [s for s in history if s["id"] == sess_id]
    assert len(matching_sessions) == 1
    session_record = matching_sessions[0]

    assert session_record["status"] == "ac"
    assert session_record["submission_count"] == 2
    assert len(session_record["submissions"]) == 2

    # Verify submission details in history
    verdicts = [sub["verdict"] for sub in session_record["submissions"]]
    assert "WA" in verdicts
    assert "AC" in verdicts

    for sub in session_record["submissions"]:
        assert sub["problem_id"] == session_record["problem_id"]
        assert sub["compiler_profile"] == "g++ (C++20)"
        assert len(sub["test_results"]) > 0


@pytest.mark.asyncio
async def test_etag_304_caching_for_problem_list_and_details(async_client: AsyncClient) -> None:
    """Test that problem list and details return ETag and respond with 304 Not Modified when unchanged."""
    # 1. Test GET /api/problems with ETag caching
    res1 = await async_client.get("/api/problems?page=1&page_size=10")
    assert res1.status_code == 200
    etag1 = res1.headers.get("etag")
    assert etag1 is not None
    assert "items" in res1.json()

    # Conditional GET with If-None-Match should return 304
    res1_cached = await async_client.get(
        "/api/problems?page=1&page_size=10",
        headers={"If-None-Match": etag1},
    )
    assert res1_cached.status_code == 304
    assert res1_cached.headers.get("etag") == etag1
    assert res1_cached.content == b""

    # 2. Test GET /api/problems/{slug} with ETag caching
    res2 = await async_client.get("/api/problems/aplusb")
    assert res2.status_code == 200
    etag2 = res2.headers.get("etag")
    assert etag2 is not None

    res2_cached = await async_client.get(
        "/api/problems/aplusb",
        headers={"If-None-Match": etag2},
    )
    assert res2_cached.status_code == 304
    assert res2_cached.headers.get("etag") == etag2

    # 3. Modify problem -> ETag changes and returns 200
    patch_res = await async_client.patch("/api/problems/aplusb", json={"difficulty": 4})
    assert patch_res.status_code == 200

    # Old ETag should no longer match
    res2_modified = await async_client.get(
        "/api/problems/aplusb",
        headers={"If-None-Match": etag2},
    )
    assert res2_modified.status_code == 200
    new_etag2 = res2_modified.headers.get("etag")
    assert new_etag2 != etag2
    assert res2_modified.json()["difficulty"] == 4


@pytest.mark.asyncio
async def test_contest_creation_and_multi_problem_endpoints(async_client: AsyncClient) -> None:
    """Test POST /api/session/start with contest name, N problems (1..14), and switch problem endpoint."""
    # 1. Start a Contest with custom name and N=2 sampled problems
    contest_name = "Speedrun Championship #1"
    start_res = await async_client.post(
        "/api/session/start",
        json={
            "name": contest_name,
            "num_problems": 2,
            "sampler_config": {
                "mean_difficulty": 3.0,
                "standard_deviation": 1.5,
                "skewness": "balanced",
                "num_problems": 2,
            },
        },
    )
    assert start_res.status_code == 200
    sess = start_res.json()
    assert sess["name"] == contest_name
    assert sess["num_problems"] == 2
    assert sess["status"] == "active"
    assert len(sess["problems"]) == 2
    assert sess["solved_count"] == 0

    first_prob = sess["problems"][0]
    second_prob = sess["problems"][1]
    assert first_prob["id"] != second_prob["id"]

    # 2. Switch problem in contest
    switch_res = await async_client.post(
        "/api/session/switch-problem",
        json={
            "session_id": sess["id"],
            "problem_id": second_prob["id"],
            "problem_index": 1,
        },
    )
    assert switch_res.status_code == 200
    switched_sess = switch_res.json()
    assert switched_sess["current_problem_index"] == 1
    assert switched_sess["problem_id"] == second_prob["id"]

    # 3. Sample N problems endpoint
    sample_res = await async_client.post(
        "/api/sampler/sample?count=3",
        json={
            "mean_difficulty": 5.0,
            "standard_deviation": 2.0,
            "num_problems": 3,
        },
    )
    assert sample_res.status_code == 200
    sampled_list = sample_res.json()
    assert isinstance(sampled_list, list)
    assert len(sampled_list) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("target_n", [1, 2, 3, 5, 7])
async def test_contest_exact_number_of_chosen_problems(
    async_client: AsyncClient, target_n: int
) -> None:
    """Test that creating a contest selects and returns the exact number of requested problems N."""
    start_res = await async_client.post(
        "/api/session/start",
        json={
            "name": f"Validation Contest N={target_n}",
            "num_problems": target_n,
            "sampler_config": {
                "mean_difficulty": 5.0,
                "standard_deviation": 2.0,
                "skewness": "balanced",
                "num_problems": target_n,
            },
        },
    )
    assert start_res.status_code == 200
    sess = start_res.json()
    assert sess["num_problems"] == target_n
    assert len(sess["problem_ids"]) == target_n
    assert len(sess["problems"]) == target_n
    # Ensure all chosen problem IDs in the contest are unique
    assert len(set(sess["problem_ids"])) == target_n

    # Verify active session also reflects the exact N chosen problems
    active_res = await async_client.get("/api/session/active")
    assert active_res.status_code == 200
    active_sess = active_res.json()
    assert active_sess is not None
    assert active_sess["num_problems"] == target_n
    assert len(active_sess["problems"]) == target_n
    assert len(active_sess["problem_ids"]) == target_n


@pytest.mark.asyncio
async def test_sync_problems_api_endpoints(async_client: AsyncClient) -> None:
    """Test sync status, background start, and cancel endpoints."""
    # 1. Get initial sync status
    status_res = await async_client.get("/api/problems/sync/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "is_running" in status_data
    assert "stage" in status_data
    assert "percent" in status_data

    # 2. Cancel endpoint when not running
    cancel_res = await async_client.post("/api/problems/sync/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] in ("not_running", "cancelling")
