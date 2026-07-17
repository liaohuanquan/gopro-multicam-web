from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters import MockCameraAdapter
from .models import (
    BatchCommandResponse,
    BatchShutterRequest,
    CameraSelection,
    CameraStatus,
    HealthResponse,
)
from .service import CameraControlService

adapter = MockCameraAdapter()
service = CameraControlService(adapter)

app = FastAPI(title="GoPro 多机控制 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", adapter=adapter.name)


@app.get("/api/cameras", response_model=list[CameraStatus])
async def list_cameras() -> list[CameraStatus]:
    return await service.list_cameras()


@app.post("/api/cameras/shutter", response_model=BatchCommandResponse)
async def set_shutter(request: BatchShutterRequest) -> BatchCommandResponse:
    return await service.set_shutter(request.camera_ids, request.action)


@app.post("/api/cameras/timecode-synced", response_model=BatchCommandResponse)
async def mark_timecode_synced(request: CameraSelection) -> BatchCommandResponse:
    return await service.mark_timecode_synced(request.camera_ids)

