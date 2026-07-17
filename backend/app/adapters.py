import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import CameraStatus, ShutterAction


class CameraUnavailableError(RuntimeError):
    pass


class CameraNotFoundError(KeyError):
    pass


class CameraAdapter(ABC):
    name: str

    @abstractmethod
    async def list_statuses(self) -> list[CameraStatus]:
        raise NotImplementedError

    @abstractmethod
    async def set_shutter(self, camera_id: str, action: ShutterAction) -> CameraStatus:
        raise NotImplementedError

    @abstractmethod
    async def mark_timecode_synced(self, camera_id: str) -> CameraStatus:
        raise NotImplementedError


@dataclass
class _MockCamera:
    id: str
    name: str
    serial: str
    location: str
    battery_percent: int
    sd_remaining_minutes: int
    temperature_c: float
    online: bool = True
    recording: bool = False
    recording_started_at: datetime | None = None
    timecode_synced_at: datetime | None = None


class MockCameraAdapter(CameraAdapter):
    """本地演示适配器，后续由 Open GoPro COHN 适配器替换。"""

    name = "mock"

    def __init__(self, cameras: list[_MockCamera] | None = None) -> None:
        self._cameras = {
            camera.id: camera
            for camera in (
                cameras
                or [
                    _MockCamera("gp13-01", "GP13-01", "C353000001", "头戴主视角", 92, 184, 41.2),
                    _MockCamera("gp13-02", "GP13-02", "C353000002", "左侧视角", 86, 176, 40.7),
                    _MockCamera("gp13-03", "GP13-03", "C353000003", "右侧视角", 78, 191, 42.1),
                    _MockCamera("gp13-04", "GP13-04", "C353000004", "环境视角", 95, 203, 39.8),
                ]
            )
        }
        self._locks = {camera_id: asyncio.Lock() for camera_id in self._cameras}

    def _get_camera(self, camera_id: str) -> _MockCamera:
        try:
            return self._cameras[camera_id]
        except KeyError as exc:
            raise CameraNotFoundError(camera_id) from exc

    @staticmethod
    def _to_status(camera: _MockCamera) -> CameraStatus:
        now = datetime.now(timezone.utc)
        recording_seconds = 0
        if camera.recording and camera.recording_started_at:
            recording_seconds = max(0, int((now - camera.recording_started_at).total_seconds()))
        return CameraStatus(
            id=camera.id,
            name=camera.name,
            serial=camera.serial,
            location=camera.location,
            online=camera.online,
            battery_percent=camera.battery_percent,
            sd_remaining_minutes=camera.sd_remaining_minutes,
            temperature_c=camera.temperature_c,
            recording=camera.recording,
            recording_seconds=recording_seconds,
            mode="4K 30 FPS · Wide · 10-bit",
            timecode_synced_at=camera.timecode_synced_at,
            last_seen_at=now,
        )

    async def list_statuses(self) -> list[CameraStatus]:
        await asyncio.sleep(0.03)
        return [self._to_status(camera) for camera in self._cameras.values()]

    async def set_shutter(self, camera_id: str, action: ShutterAction) -> CameraStatus:
        camera = self._get_camera(camera_id)
        async with self._locks[camera_id]:
            await asyncio.sleep(0.08)
            if not camera.online:
                raise CameraUnavailableError(f"{camera.name} 当前离线")
            if action is ShutterAction.START and not camera.recording:
                camera.recording = True
                camera.recording_started_at = datetime.now(timezone.utc)
            elif action is ShutterAction.STOP and camera.recording:
                camera.recording = False
                camera.recording_started_at = None
            return self._to_status(camera)

    async def mark_timecode_synced(self, camera_id: str) -> CameraStatus:
        camera = self._get_camera(camera_id)
        async with self._locks[camera_id]:
            if not camera.online:
                raise CameraUnavailableError(f"{camera.name} 当前离线")
            camera.timecode_synced_at = datetime.now(timezone.utc)
            return self._to_status(camera)
