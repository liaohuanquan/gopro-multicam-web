from datetime import datetime, timezone

import pytest

from app.media_clipper import MediaClipper
from app.models import TaskEvent, TaskEventType


def event(event_id: str, task_id: str, event_type: TaskEventType, second: int) -> TaskEvent:
    created_at = datetime(2026, 7, 22, 8, 10, second, tzinfo=timezone.utc)
    return TaskEvent(
        id=event_id,
        task_id=task_id,
        task_name=task_id,
        event=event_type,
        utc_at=created_at,
        created_at=created_at,
        countdown_seconds=0,
    )


def test_pairs_only_completed_tasks_in_start_order() -> None:
    events = [
        event("s2", "task-2", TaskEventType.START, 20),
        event("e1", "task-1", TaskEventType.END, 10),
        event("s1", "task-1", TaskEventType.START, 0),
    ]

    pairs = MediaClipper._pair_tasks(events)

    assert [(start.task_id, end.task_id) for start, end in pairs] == [("task-1", "task-1")]


def test_combines_mp4_date_with_frame_accurate_timecode() -> None:
    created_at = datetime(2026, 7, 22, 8, 10, 16, tzinfo=timezone.utc)

    result = MediaClipper._combine_timecode(created_at, "08:10:15:15", 30)

    assert result == datetime(2026, 7, 22, 8, 10, 15, 500000, tzinfo=timezone.utc)


def test_rejects_invalid_timecode() -> None:
    with pytest.raises(RuntimeError, match="无法解析"):
        MediaClipper._combine_timecode(datetime.now(timezone.utc), "bad", 30)


@pytest.mark.parametrize(
    ("camera_count", "layout"),
    [
        (2, "layout=0_0|960_0"),
        (3, "layout=0_0|960_0|480_540"),
        (4, "layout=0_0|960_0|0_540|960_540"),
    ],
)
def test_builds_grid_layout_for_camera_count(camera_count: int, layout: str) -> None:
    filter_complex = MediaClipper._grid_filter(camera_count)

    assert f"xstack=inputs={camera_count}" in filter_complex
    assert layout in filter_complex


def test_does_not_build_single_camera_grid() -> None:
    with pytest.raises(RuntimeError, match="2 至 4 台"):
        MediaClipper._grid_filter(1)
