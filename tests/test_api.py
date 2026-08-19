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
    """Test listing problems with category and difficulty filters."""
    res = await async_client.get("/api/problems?min_difficulty=1&max_difficulty=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] > 0
    assert len(data["items"]) > 0


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

    # 4. Request AI refinement
    submission_id = sub_data["submission"]["id"]
    refine_res = await async_client.post(f"/api/submissions/{submission_id}/refine")
    assert refine_res.status_code == 200
    review_data = refine_res.json()
    assert review_data["submission_id"] == submission_id
    assert len(review_data["suggestions"]) > 0
