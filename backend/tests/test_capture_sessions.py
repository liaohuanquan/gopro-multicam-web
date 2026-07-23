import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.adapters import CameraMediaFile
from app.capture_sessions import CaptureSessionStore
from app.models import CameraStatus, TaskEvent, TaskEventListResponse, TaskEventType


class FakeAdapter:
    def __init__(self) -> None:
        self.after_recording = False
        self.media_failures_remaining = 0
        self.late_old_media = False
        self.download_waiter: asyncio.Event | None = None

    async def list_statuses(self):
        return [CameraStatus(
            id="camera-1",
            name="GP01",
            serial="camera-1",
            location="未设置",
            online=True,
            recording=False,
            recording_seconds=0,
            mode="4K 30 FPS",
            last_seen_at=datetime.now(timezone.utc),
        )]

    async def list_media(self, camera_id: str):
        if self.after_recording and self.media_failures_remaining > 0:
            self.media_failures_remaining -= 1
            raise RuntimeError("媒体索引尚未刷新")
        files = [CameraMediaFile("100GOPRO/GX010001.MP4", 3)]
        if self.after_recording:
            files.append(CameraMediaFile(
                "100GOPRO/GX010002.MP4",
                5,
                datetime.now(timezone.utc),
            ))
            if self.late_old_media:
                files.append(CameraMediaFile(
                    "100GOPRO/GX019999.MP4",
                    5,
                    datetime.now(timezone.utc) - timedelta(hours=1),
                ))
        return files

    async def download_media(self, camera_id: str, remote_path: str, destination: Path, progress):
        if self.download_waiter is not None:
            await self.download_waiter.wait()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        await progress(5)
        return 5


class FakeClipper:
    _pair_tasks = staticmethod(__import__("app.media_clipper", fromlist=["MediaClipper"]).MediaClipper._pair_tasks)

    async def create_clips(self, session, session_dir: Path, events) -> int:
        tasks = self._pair_tasks(events)
        for index, _ in enumerate(tasks, start=1):
            output = session_dir / "clips" / f"task_{index:03d}" / "GP01.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"clip")
        return len(tasks)


async def test_collects_only_new_media_into_session_directory(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    store = CaptureSessionStore(tmp_path / "sessions", adapter, finalize_delay=0)
    session = await store.begin(["camera-1"])
    adapter.after_recording = True

    await store.start_collection(
        session.id,
        TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=[]),
    )
    while (await store.get(session.id)).status == "collecting":
        await asyncio.sleep(0.01)

    result = await store.get(session.id)
    session_dir = tmp_path / "sessions" / session.id
    assert result.status == "complete"
    assert result.files_total == 1
    assert result.files_completed == 1
    assert (session_dir / "source" / "GP01" / "GX010002.MP4").read_bytes() == b"video"
    assert (session_dir / "task_events.json").exists()
    assert (session_dir / "clips").is_dir()


async def test_creates_numbered_task_clips_after_collection(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    store = CaptureSessionStore(tmp_path / "sessions", adapter, finalize_delay=0, clipper=FakeClipper())
    session = await store.begin(["camera-1"])
    adapter.after_recording = True
    start_at = session.started_at
    end_at = start_at + timedelta(seconds=1)
    events = [
        TaskEvent(
            id="start-1", task_id="task-1", task_name="任务 01", event=TaskEventType.START,
            utc_at=start_at, created_at=start_at, countdown_seconds=0,
        ),
        TaskEvent(
            id="end-1", task_id="task-1", task_name="任务 01", event=TaskEventType.END,
            utc_at=end_at, created_at=start_at, countdown_seconds=0,
        ),
    ]

    await store.start_collection(
        session.id,
        TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=events),
    )
    while (await store.get(session.id)).status == "collecting":
        await asyncio.sleep(0.01)

    result = await store.get(session.id)
    output = tmp_path / "sessions" / session.id / "clips" / "task_001" / "GP01.mp4"
    assert result.status == "complete"
    assert result.clips_total == 1
    assert result.clips_completed == 1
    assert output.read_bytes() == b"clip"


async def test_retries_media_list_after_recording_stops(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    store = CaptureSessionStore(
        tmp_path / "sessions",
        adapter,
        finalize_delay=0,
        media_list_retry_interval=0.01,
    )
    session = await store.begin(["camera-1"])
    adapter.after_recording = True
    adapter.media_failures_remaining = 2

    await store.start_collection(
        session.id,
        TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=[]),
    )
    while (await store.get(session.id)).status == "collecting":
        await asyncio.sleep(0.01)

    result = await store.get(session.id)
    assert result.status == "complete"
    assert result.files_completed == 1
    assert adapter.media_failures_remaining == 0


async def test_collects_every_media_path_added_after_baseline(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    store = CaptureSessionStore(tmp_path / "sessions", adapter, finalize_delay=0)
    session = await store.begin(["camera-1"])
    adapter.after_recording = True
    adapter.late_old_media = True

    await store.start_collection(
        session.id,
        TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=[]),
    )
    while (await store.get(session.id)).status == "collecting":
        await asyncio.sleep(0.01)

    result = await store.get(session.id)
    assert [item.remote_path for item in result.collected_files] == [
        "100GOPRO/GX010002.MP4",
        "100GOPRO/GX019999.MP4",
    ]


async def test_cancels_active_collection(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    adapter.download_waiter = asyncio.Event()
    store = CaptureSessionStore(tmp_path / "sessions", adapter, finalize_delay=0)
    session = await store.begin(["camera-1"])
    adapter.after_recording = True
    await store.start_collection(
        session.id,
        TaskEventListResponse(server_utc=datetime.now(timezone.utc), events=[]),
    )
    while (await store.get(session.id)).files_total == 0:
        await asyncio.sleep(0.01)

    result = await store.cancel_collection(session.id)

    assert result.status == "cancelled"
    assert result.files_completed == 0
