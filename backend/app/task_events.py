import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import CreateTaskEventRequest, TaskEvent, TaskEventListResponse, TaskEventType


class TaskEventConflictError(RuntimeError):
    pass


class TaskEventStore:
    """持久化采集任务的 UTC 切片事件。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    def _load(self) -> list[TaskEvent]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return [TaskEvent.model_validate(item) for item in payload.get("events", [])]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"任务事件文件损坏：{self._path}") from exc

    def _save(self, events: list[TaskEvent]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                {"events": [event.model_dump(mode="json") for event in events]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.chmod(0o600)
        temporary_path.replace(self._path)

    async def list_events(self) -> TaskEventListResponse:
        async with self._lock:
            events = self._load()
        return TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=events)

    async def clear(self) -> None:
        """开始新的采集会话时清空上一会话的任务切点。"""
        async with self._lock:
            self._save([])

    async def create(self, request: CreateTaskEventRequest) -> TaskEvent:
        async with self._lock:
            events = self._load()
            active = self._active_event(events)
            now = datetime.now(timezone.utc)

            if events and events[-1].utc_at > now:
                raise TaskEventConflictError("上一个任务切点仍在倒计时")

            if request.event is TaskEventType.START:
                if active is not None:
                    raise TaskEventConflictError(f"任务“{active.task_name}”尚未结束")
                task_id = request.task_id or uuid4().hex[:12]
            else:
                if active is None:
                    raise TaskEventConflictError("当前没有正在进行的任务")
                if request.task_id and request.task_id != active.task_id:
                    raise TaskEventConflictError("结束事件与当前任务不匹配")
                task_id = active.task_id

            created_at = now
            event = TaskEvent(
                id=uuid4().hex,
                task_id=task_id,
                task_name=request.task_name.strip(),
                event=request.event,
                utc_at=created_at + timedelta(seconds=request.countdown_seconds),
                created_at=created_at,
                countdown_seconds=request.countdown_seconds,
            )
            events.append(event)
            self._save(events)
            return event

    @staticmethod
    def _active_event(events: list[TaskEvent]) -> TaskEvent | None:
        active: TaskEvent | None = None
        for event in events:
            if event.event is TaskEventType.START:
                active = event
            elif active is not None and event.task_id == active.task_id:
                active = None
        return active
