from pathlib import Path

from app.models import CreateTaskEventRequest, TaskEventType
from app.task_events import TaskEventStore


async def test_clear_removes_events_from_previous_session(tmp_path: Path) -> None:
    store = TaskEventStore(tmp_path / "task_events.json")
    await store.create(CreateTaskEventRequest(
        task_name="旧任务",
        event=TaskEventType.START,
        countdown_seconds=0,
    ))

    await store.clear()

    assert (await store.list_events()).events == []
