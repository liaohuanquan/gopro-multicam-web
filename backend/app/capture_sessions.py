import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .adapters import CameraMediaFile, CohnCameraAdapter
from .media_clipper import MediaClipper
from .models import CaptureSession, CollectedFile, TaskEventListResponse


class CaptureSessionNotFoundError(KeyError):
    pass


class CaptureSessionStore:
    """管理一次连续录制及其局域网素材收集结果。"""

    def __init__(
        self,
        root: Path,
        adapter: CohnCameraAdapter,
        finalize_delay: float = 15.0,
        clipper: MediaClipper | None = None,
        media_list_retry_timeout: float = 60.0,
        media_list_retry_interval: float = 2.0,
    ) -> None:
        self._root = root
        self._adapter = adapter
        self._finalize_delay = finalize_delay
        self._clipper = clipper or MediaClipper()
        self._media_list_retry_timeout = media_list_retry_timeout
        self._media_list_retry_interval = media_list_retry_interval
        self._sessions: dict[str, CaptureSession] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._collection_tasks: dict[str, asyncio.Task] = {}

    def _session_dir(self, session_id: str) -> Path:
        return self._root / session_id

    async def _save(self, session: CaptureSession) -> None:
        directory = self._session_dir(session.id)
        directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(session.model_dump(mode="json"), ensure_ascii=False, indent=2)
        temporary = directory / "session.json.tmp"
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(directory / "session.json")

    async def begin(self, camera_ids: list[str]) -> CaptureSession:
        statuses = {camera.id: camera for camera in await self._adapter.list_statuses()}
        missing = [camera_id for camera_id in camera_ids if camera_id not in statuses or not statuses[camera_id].online]
        if missing:
            raise RuntimeError(f"以下相机离线，无法开始采集：{', '.join(missing)}")

        media_lists = await asyncio.gather(*(self._adapter.list_media(camera_id) for camera_id in camera_ids))
        started_at = datetime.now(timezone.utc)
        session_id = f"session_{started_at.strftime('%Y%m%d_%H%M%S_%f')}"
        session = CaptureSession(
            id=session_id,
            status="recording",
            started_at=started_at,
            camera_ids=camera_ids,
            camera_names={camera_id: statuses[camera_id].name for camera_id in camera_ids},
            baseline_media={
                camera_id: [item.path for item in media]
                for camera_id, media in zip(camera_ids, media_lists, strict=True)
            },
        )
        async with self._lock:
            self._sessions[session_id] = session
            await self._save(session)
        return session

    async def get(self, session_id: str) -> CaptureSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            path = self._session_dir(session_id) / "session.json"
            if not path.exists():
                raise CaptureSessionNotFoundError(session_id) from exc
            session = CaptureSession.model_validate_json(path.read_text(encoding="utf-8"))
            self._sessions[session_id] = session
            return session

    async def add_errors(self, session_id: str, errors: list[str]) -> CaptureSession:
        session = await self.get(session_id)
        session.errors.extend(errors)
        await self._save(session)
        return session

    async def start_collection(self, session_id: str, task_events: TaskEventListResponse) -> CaptureSession:
        session = await self.get(session_id)
        if session.status not in {"recording", "collection_failed"}:
            return session
        session.status = "collecting"
        session.stopped_at = datetime.now(timezone.utc)
        await self._save(session)
        task = asyncio.create_task(self._collect(session, task_events))
        self._tasks.add(task)
        self._collection_tasks[session.id] = task

        def collection_done(completed: asyncio.Task) -> None:
            self._tasks.discard(completed)
            if self._collection_tasks.get(session.id) is completed:
                self._collection_tasks.pop(session.id, None)

        task.add_done_callback(collection_done)
        return session

    async def cancel_collection(self, session_id: str) -> CaptureSession:
        session = await self.get(session_id)
        if session.status != "collecting":
            return session
        task = self._collection_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        session.status = "cancelled"
        await self._save(session)
        return session

    async def _list_media_after_finalize(self, camera_id: str) -> list[CameraMediaFile]:
        """录像停止后相机需要短暂时间刷新媒体索引。"""
        deadline = monotonic() + self._media_list_retry_timeout
        while True:
            try:
                return await self._adapter.list_media(camera_id)
            except Exception as exc:  # 保留最后一次相机错误供会话展示
                if monotonic() >= deadline:
                    raise exc
                await asyncio.sleep(self._media_list_retry_interval)

    async def _collect(self, session: CaptureSession, task_events: TaskEventListResponse) -> None:
        try:
            await asyncio.sleep(self._finalize_delay)
            session_dir = self._session_dir(session.id)
            (session_dir / "source").mkdir(parents=True, exist_ok=True)
            (session_dir / "clips").mkdir(parents=True, exist_ok=True)

            bounded_events = [
                event for event in task_events.events
                if session.started_at <= event.created_at <= (session.stopped_at or datetime.now(timezone.utc))
            ]
            events_payload = task_events.model_dump(mode="json")
            events_payload["events"] = [event.model_dump(mode="json") for event in bounded_events]
            (session_dir / "task_events.json").write_text(
                json.dumps(events_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            media_by_camera: dict[str, list[CameraMediaFile]] = {}
            for camera_id in session.camera_ids:
                try:
                    current = await self._list_media_after_finalize(camera_id)
                    baseline = set(session.baseline_media.get(camera_id, []))
                    media_by_camera[camera_id] = [
                        item for item in current
                        if item.path not in baseline
                    ]
                except Exception as exc:  # 单台失败不阻塞其他相机收集
                    session.errors.append(str(exc))
                    media_by_camera[camera_id] = []

            pending_files = [
                (camera_id, media)
                for camera_id, files in media_by_camera.items()
                for media in files
            ]
            session.files_total = len(pending_files)
            session.bytes_total = sum(media.size_bytes for _, media in pending_files)
            await self._save(session)

            semaphore = asyncio.Semaphore(2)

            async def download(camera_id: str, media: CameraMediaFile) -> None:
                camera_name = session.camera_names[camera_id]
                destination = session_dir / "source" / camera_name / Path(media.path).name

                async def progress(size: int) -> None:
                    session.bytes_downloaded += size

                async with semaphore:
                    try:
                        size = await self._adapter.download_media(camera_id, media.path, destination, progress)
                        session.collected_files.append(CollectedFile(
                            camera_id=camera_id,
                            camera_name=camera_name,
                            remote_path=media.path,
                            local_path=str(destination.relative_to(session_dir)),
                            size_bytes=size,
                        ))
                        session.files_completed += 1
                    except Exception as exc:  # 下载失败保留任务状态供界面显示
                        session.errors.append(str(exc))
                    await self._save(session)

            await asyncio.gather(*(download(camera_id, media) for camera_id, media in pending_files))
            paired_tasks = self._clipper._pair_tasks(bounded_events)
            session.clips_total = len(paired_tasks) * len(session.camera_ids)
            await self._save(session)
            if session.files_completed == session.files_total and paired_tasks:
                session.clips_completed = await self._clipper.create_clips(session, session_dir, bounded_events)
                if len(session.camera_ids) > 1:
                    session.grids_total = len(paired_tasks)
                    await self._save(session)
                    session.grids_completed = await self._clipper.create_grid_previews(
                        session,
                        session_dir,
                        len(paired_tasks),
                    )
            session.status = "complete" if not session.errors else "partial"
            await self._save(session)
        except Exception as exc:
            session.status = "collection_failed"
            session.errors.append(str(exc))
            await self._save(session)
