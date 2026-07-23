from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ShutterAction(str, Enum):
    START = "start"
    STOP = "stop"


class TaskEventType(str, Enum):
    START = "start"
    END = "end"


class CameraStatus(BaseModel):
    id: str
    name: str
    serial: str
    location: str
    online: bool
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    sd_remaining_minutes: int | None = Field(default=None, ge=0)
    sd_remaining_gb: float | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    overheating: bool | None = None
    recording: bool
    recording_seconds: int = Field(ge=0)
    mode: str
    timecode_synced_at: datetime | None = None
    last_seen_at: datetime


class CameraSelection(BaseModel):
    camera_ids: list[str] = Field(min_length=1)


class BatchShutterRequest(CameraSelection):
    action: ShutterAction


class CommandResult(BaseModel):
    camera_id: str
    success: bool
    message: str
    status: CameraStatus | None = None


class BatchCommandResponse(BaseModel):
    success_count: int
    failure_count: int
    results: list[CommandResult]


class HealthResponse(BaseModel):
    status: str
    adapter: str


class DiscoverCameraRequest(BaseModel):
    profile_label: str = Field(default="4K 30 FPS · Wide · 10-bit", max_length=128)


class RecordingConfig(BaseModel):
    resolution: Literal["1080P", "4K", "5.3K_8_7"] | None = None
    fps: Literal[24, 25, 30, 50, 60] | None = None
    lens: Literal["wide", "linear", "hyperview"] | None = None
    bit_depth: Literal[8, 10] | None = None
    color: Literal["natural", "flat", "vibrant"] | None = None
    high_bitrate: bool | None = None
    stabilization: Literal["off", "high", "auto_boost"] | None = None
    hindsight: bool | None = None
    shutter_speed: Literal[0, 120, 240, 480] | None = None
    iso: Literal[100, 200, 400, 800, 1600] | None = None


class DiscoveryResponse(BaseModel):
    discovered_count: int = Field(ge=0)
    cameras: list[CameraStatus]


class UpdateCameraRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class CreateTaskEventRequest(BaseModel):
    task_id: str | None = Field(default=None, min_length=1, max_length=64)
    task_name: str = Field(min_length=1, max_length=64)
    event: TaskEventType
    countdown_seconds: int = Field(default=3, ge=0, le=10)


class TaskEvent(BaseModel):
    id: str
    task_id: str
    task_name: str
    event: TaskEventType
    utc_at: datetime
    created_at: datetime
    countdown_seconds: int = Field(ge=0, le=10)


class TaskEventListResponse(BaseModel):
    server_utc: datetime
    events: list[TaskEvent]


class CaptureSessionRequest(CameraSelection):
    pass


class CollectedFile(BaseModel):
    camera_id: str
    camera_name: str
    remote_path: str
    local_path: str
    size_bytes: int = Field(ge=0)


class EgoMediaFile(BaseModel):
    stream: Literal["left", "right"]
    local_path: str
    original_name: str
    size_bytes: int = Field(ge=0)


class CaptureSession(BaseModel):
    id: str
    status: str
    started_at: datetime
    stopped_at: datetime | None = None
    camera_ids: list[str]
    camera_names: dict[str, str]
    baseline_media: dict[str, list[str]]
    files_total: int = Field(default=0, ge=0)
    files_completed: int = Field(default=0, ge=0)
    bytes_total: int = Field(default=0, ge=0)
    bytes_downloaded: int = Field(default=0, ge=0)
    collected_files: list[CollectedFile] = Field(default_factory=list)
    ego_files: list[EgoMediaFile] = Field(default_factory=list)
    timesync_ready: bool = False
    task_count: int = Field(default=0, ge=0)
    clips_total: int = Field(default=0, ge=0)
    clips_completed: int = Field(default=0, ge=0)
    grids_total: int = Field(default=0, ge=0)
    grids_completed: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)


class SyncValidationCameraResult(BaseModel):
    camera_id: str
    camera_name: str
    decoded_frames: int = Field(ge=0)
    compared_frames: int = Field(ge=0)
    offset_frames: float | None = None
    jitter_frames: float | None = None


class SyncValidationReport(BaseModel):
    session_id: str
    reference_camera_id: str
    reference_camera_name: str
    target_fps: int = 30
    results: list[SyncValidationCameraResult]


class TimelineSyncDeviceResult(BaseModel):
    device_id: str
    device_name: str
    role: Literal["ego", "exo"]
    stream: str
    total_frames: int = Field(ge=0)
    decoded_qr_frames: int = Field(ge=0)
    inlier_qr_frames: int = Field(ge=0)
    anchor_span_seconds: float = Field(ge=0)
    slope: float
    intercept: float
    fit_rmse_ms: float = Field(ge=0)
    median_match_error_ms: float | None = Field(default=None, ge=0)
    max_match_error_ms: float | None = Field(default=None, ge=0)


class TimelineSyncReport(BaseModel):
    session_id: str
    reference_device_id: str = "EGO_LEFT"
    reference_device_name: str = "EGO 左目"
    target_fps: int = 30
    timeline_rows: int = Field(ge=0)
    devices: list[TimelineSyncDeviceResult]
