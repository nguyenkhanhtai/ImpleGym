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
    res = await async_client.get("/api/problems?min_difficulty=1&max_difficulty=10&page=1&page_size=2")
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
    assert sess_data["problem"]["target_time_seconds"] == sess_data["problem"]["difficulty"] * 5 * 60.0

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
    assert res_data["session"]["total_duration_seconds"] <= res_data["session"]["target_time_seconds"]

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
    routes = ["/", "/explorer", "/gym", "/history", "/forge"]
    for route in routes:
        res = await async_client.get(route)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "<!DOCTYPE html>" in res.text
        assert "ImpleGym" in res.text

