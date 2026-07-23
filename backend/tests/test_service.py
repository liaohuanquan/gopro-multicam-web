from datetime import datetime, timezone

from app.adapters import CameraUnavailableError
from app.models import CameraStatus
from app.service import CameraControlService


async def test_recording_config_retries_until_camera_recovers() -> None:
    class RecoveringAdapter:
        attempts = 0

        async def apply_recording_config(self, camera_id: str) -> CameraStatus:
            self.attempts += 1
            if self.attempts < 3:
                raise CameraUnavailableError("相机正在重新连接")
            return CameraStatus(
                id=camera_id,
                name="GP02",
                serial="serial",
                location="",
                online=True,
                recording=False,
                recording_seconds=0,
                mode="ready",
                last_seen_at=datetime.now(timezone.utc),
            )

    adapter = RecoveringAdapter()
    service = CameraControlService(
        adapter,  # type: ignore[arg-type]
        recording_config_retry_timeout=1,
        recording_config_retry_interval=0,
    )

    result = await service.apply_recording_config(["camera-1"])

    assert adapter.attempts == 3
    assert result.success_count == 1
    assert result.failure_count == 0
