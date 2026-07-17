from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ShutterAction(str, Enum):
    START = "start"
    STOP = "stop"


class CameraStatus(BaseModel):
    id: str
    name: str
    serial: str
    location: str
    online: bool
    battery_percent: int = Field(ge=0, le=100)
    sd_remaining_minutes: int = Field(ge=0)
    temperature_c: float
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
