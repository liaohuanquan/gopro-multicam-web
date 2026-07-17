import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_lists_four_cameras(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/cameras")

    assert response.status_code == 200
    assert len(response.json()) == 4


async def test_starts_and_stops_selected_cameras(client: httpx.AsyncClient) -> None:
    start_response = await client.post(
        "/api/cameras/shutter",
        json={"camera_ids": ["gp13-01", "gp13-02"], "action": "start"},
    )

    assert start_response.status_code == 200
    assert start_response.json()["success_count"] == 2
    assert all(result["status"]["recording"] for result in start_response.json()["results"])

    stop_response = await client.post(
        "/api/cameras/shutter",
        json={"camera_ids": ["gp13-01", "gp13-02"], "action": "stop"},
    )
    assert stop_response.json()["success_count"] == 2
    assert not any(result["status"]["recording"] for result in stop_response.json()["results"])


async def test_marks_timecode_sync_for_selection(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/cameras/timecode-synced",
        json={"camera_ids": ["gp13-03", "gp13-04"]},
    )

    assert response.status_code == 200
    assert response.json()["success_count"] == 2
    assert all(result["status"]["timecode_synced_at"] for result in response.json()["results"])


async def test_reports_unknown_camera_without_failing_batch(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/cameras/shutter",
        json={"camera_ids": ["gp13-01", "missing"], "action": "start"},
    )

    assert response.status_code == 200
    assert response.json()["success_count"] == 1
    assert response.json()["failure_count"] == 1
