import asyncio

from .adapters import CameraAdapter, CameraNotFoundError, CameraUnavailableError
from .models import BatchCommandResponse, CameraStatus, CommandResult, ShutterAction


class CameraControlService:
    def __init__(
        self,
        adapter: CameraAdapter,
        recording_config_retry_timeout: float = 60.0,
        recording_config_retry_interval: float = 5.0,
    ) -> None:
        self.adapter = adapter
        self._recording_config_retry_timeout = recording_config_retry_timeout
        self._recording_config_retry_interval = recording_config_retry_interval

    async def list_cameras(self) -> list[CameraStatus]:
        return await self.adapter.list_statuses()

    async def set_shutter(
        self, camera_ids: list[str], action: ShutterAction
    ) -> BatchCommandResponse:
        results = await asyncio.gather(
            *(self._set_single_shutter(camera_id, action) for camera_id in camera_ids)
        )
        return self._build_response(results)

    async def mark_timecode_synced(self, camera_ids: list[str]) -> BatchCommandResponse:
        results = await asyncio.gather(
            *(self._mark_single_timecode(camera_id) for camera_id in camera_ids)
        )
        return self._build_response(results)

    async def apply_recording_config(self, camera_ids: list[str]) -> BatchCommandResponse:
        results = await asyncio.gather(
            *(self._apply_single_recording_config(camera_id) for camera_id in camera_ids)
        )
        return self._build_response(results)

    async def _set_single_shutter(
        self, camera_id: str, action: ShutterAction
    ) -> CommandResult:
        try:
            status = await self.adapter.set_shutter(camera_id, action)
            action_text = "开始录制" if action is ShutterAction.START else "停止录制"
            return CommandResult(
                camera_id=camera_id,
                success=True,
                message=f"{status.name} 已{action_text}",
                status=status,
            )
        except (CameraNotFoundError, CameraUnavailableError) as exc:
            return CommandResult(camera_id=camera_id, success=False, message=str(exc))

    async def _mark_single_timecode(self, camera_id: str) -> CommandResult:
        try:
            status = await self.adapter.mark_timecode_synced(camera_id)
            return CommandResult(
                camera_id=camera_id,
                success=True,
                message=f"{status.name} 已记录时间码同步",
                status=status,
            )
        except (CameraNotFoundError, CameraUnavailableError) as exc:
            return CommandResult(camera_id=camera_id, success=False, message=str(exc))

    async def _apply_single_recording_config(self, camera_id: str) -> CommandResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._recording_config_retry_timeout
        while True:
            try:
                status = await self.adapter.apply_recording_config(camera_id)
                return CommandResult(
                    camera_id=camera_id,
                    success=True,
                    message=f"{status.name} 已应用录制参数",
                    status=status,
                )
            except CameraNotFoundError as exc:
                return CommandResult(camera_id=camera_id, success=False, message=str(exc))
            except CameraUnavailableError as exc:
                if loop.time() >= deadline:
                    return CommandResult(camera_id=camera_id, success=False, message=str(exc))
                await asyncio.sleep(self._recording_config_retry_interval)

    @staticmethod
    def _build_response(results: list[CommandResult]) -> BatchCommandResponse:
        success_count = sum(result.success for result in results)
        return BatchCommandResponse(
            success_count=success_count,
            failure_count=len(results) - success_count,
            results=results,
        )
