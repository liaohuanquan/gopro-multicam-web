import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .adapters import CameraMediaFile, CohnCameraAdapter
from .media_clipper import MediaClipper
from .models import CaptureSession, CollectedFile, EgoMediaFile, TaskEventListResponse


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
        self._processing_tasks: dict[str, asyncio.Task] = {}

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
            self._hydrate_task_count(session)
            self._sessions[session_id] = session
            return session

    def _hydrate_task_count(self, session: CaptureSession) -> None:
        """兼容尚未持久化 task_count 的历史 Session。"""
        if session.task_count > 0:
            return
        event_path = self._session_dir(session.id) / "task_events.json"
        if not event_path.exists():
            return
        try:
            task_events = TaskEventListResponse.model_validate_json(event_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        session.task_count = len(self._clipper._pair_tasks(task_events.events))

    async def list_sessions(self) -> list[CaptureSession]:
        sessions: list[CaptureSession] = []
        if not self._root.exists():
            return sessions
        for path in self._root.glob("session_*/session.json"):
            try:
                session = CaptureSession.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self._hydrate_task_count(session)
            self._sessions[session.id] = session
            sessions.append(session)
        return sorted(sessions, key=lambda item: item.started_at, reverse=True)

    async def add_errors(self, session_id: str, errors: list[str]) -> CaptureSession:
        session = await self.get(session_id)
        session.errors.extend(errors)
        await self._save(session)
        return session

    async def save_ego_media(
        self,
        session_id: str,
        stream: str,
        original_name: str,
        chunks,
    ) -> CaptureSession:
        """保存无法通过局域网收集的 EGO 左右目素材。"""
        session = await self.get(session_id)
        if session.status not in {"complete", "partial"}:
            raise RuntimeError("请等待 EXO 素材收集完成后再导入 EGO 素材")
        if stream not in {"left", "right"}:
            raise RuntimeError("EGO 流只能是 left 或 right")

        suffix = Path(original_name).suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise RuntimeError("EGO 素材仅支持 MP4 或 MOV")
        directory = self._session_dir(session_id) / "source" / "EGO"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{stream.upper()}{suffix}"
        temporary = destination.with_suffix(destination.suffix + ".part")
        size = 0
        try:
            with temporary.open("wb") as output:
                async for chunk in chunks:
                    if chunk:
                        output.write(chunk)
                        size += len(chunk)
            if size == 0:
                raise RuntimeError("EGO 素材为空")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

        session.ego_files = [item for item in session.ego_files if item.stream != stream]
        session.ego_files.append(EgoMediaFile(
            stream=stream,
            local_path=str(destination.relative_to(self._session_dir(session_id))),
            original_name=Path(original_name).name,
            size_bytes=size,
        ))
        session.timesync_ready = False
        await self._save(session)
        return session

    async def mark_timesync_ready(self, session_id: str) -> CaptureSession:
        session = await self.get(session_id)
        session.timesync_ready = True
        await self._save(session)
        return session

    async def start_processing(self, session_id: str) -> CaptureSession:
        session = await self.get(session_id)
        if session.status == "processing":
            return session
        if session.status not in {"collected", "complete", "process_failed"}:
            raise RuntimeError("当前 Session 尚未完成素材回收")
        session.status = "processing"
        session.errors = []
        session.clips_total = 0
        session.clips_completed = 0
        session.grids_total = 0
        session.grids_completed = 0
        await self._save(session)

        task = asyncio.create_task(self._process(session))
        self._tasks.add(task)
        self._processing_tasks[session.id] = task

        def processing_done(completed: asyncio.Task) -> None:
            self._tasks.discard(completed)
            if self._processing_tasks.get(session.id) is completed:
                self._processing_tasks.pop(session.id, None)

        task.add_done_callback(processing_done)
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
            session.task_count = len(self._clipper._pair_tasks(bounded_events))

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
            session.status = "collected" if not session.errors else "partial"
            await self._save(session)
        except Exception as exc:
            session.status = "collection_failed"
            session.errors.append(str(exc))
            await self._save(session)

    async def _process(self, session: CaptureSession) -> None:
        try:
            session_dir = self._session_dir(session.id)
            event_path = session_dir / "task_events.json"
            if not event_path.exists():
                raise RuntimeError("Session 缺少 task_events.json")
            task_events = TaskEventListResponse.model_validate_json(event_path.read_text(encoding="utf-8"))
            paired_tasks = self._clipper._pair_tasks(task_events.events)
            if not paired_tasks:
                raise RuntimeError("Session 中没有完整的任务开始和结束切点")
            if session.files_completed != session.files_total:
                raise RuntimeError("Session 素材回收不完整，无法生成切片")

            session.clips_total = len(paired_tasks) * len(session.camera_ids)
            session.grids_total = len(paired_tasks) if len(session.camera_ids) > 1 else 0
            await self._save(session)
            session.clips_completed = await self._clipper.create_clips(
                session,
                session_dir,
                task_events.events,
            )
            await self._save(session)
            if session.grids_total:
                session.grids_completed = await self._clipper.create_grid_previews(
                    session,
                    session_dir,
                    len(paired_tasks),
                )
            session.status = "complete"
            await self._save(session)
        except Exception as exc:
            session.status = "process_failed"
            session.errors.append(str(exc))
            await self._save(session)
