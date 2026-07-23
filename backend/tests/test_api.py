import asyncio
import os
import tempfile
from datetime import datetime

import httpx
import pytest

os.environ["GOPRO_DATA_DIR"] = tempfile.mkdtemp(prefix="gopro-api-tests-")

from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_device_group_starts_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/cameras")

    assert response.status_code == 200
    assert response.json() == []


async def test_health_reports_real_cohn_adapter(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.json() == {"status": "ok", "adapter": "cohn"}


async def test_unknown_camera_is_reported_per_batch(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/cameras/shutter",
        json={"camera_ids": ["missing"], "action": "start"},
    )

    assert response.status_code == 200
    assert response.json()["failure_count"] == 1


async def test_task_events_record_server_utc_boundaries(client: httpx.AsyncClient) -> None:
    start_response = await client.post(
        "/api/task-events",
        json={
            "task_name": "拿取水杯",
            "event": "start",
            "countdown_seconds": 1,
        },
    )

    assert start_response.status_code == 201
    start_event = start_response.json()
    assert start_event["task_name"] == "拿取水杯"
    assert start_event["event"] == "start"
    parse_api_datetime = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parse_api_datetime(start_event["utc_at"]) > parse_api_datetime(start_event["created_at"])

    countdown_conflict = await client.post(
        "/api/task-events",
        json={"task_name": "拿取水杯", "event": "end", "countdown_seconds": 0},
    )
    assert countdown_conflict.status_code == 409

    await asyncio.sleep(1.05)

    end_response = await client.post(
        "/api/task-events",
        json={
            "task_id": start_event["task_id"],
            "task_name": start_event["task_name"],
            "event": "end",
            "countdown_seconds": 3,
        },
    )

    assert end_response.status_code == 201
    events_response = await client.get("/api/task-events")
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert [event["event"] for event in events[-2:]] == ["start", "end"]
    assert events[-1]["task_id"] == start_event["task_id"]
