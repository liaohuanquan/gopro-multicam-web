import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .adapters import CameraNotFoundError, CameraRegistrationError, CameraUnavailableError, CohnCameraAdapter
from .capture_sessions import CaptureSessionNotFoundError, CaptureSessionStore
from .models import (
    BatchCommandResponse,
    BatchShutterRequest,
    CameraSelection,
    CameraStatus,
    CaptureSession,
    CaptureSessionRequest,
    DiscoverCameraRequest,
    DiscoveryResponse,
    HealthResponse,
    RecordingConfig,
    CreateTaskEventRequest,
    TaskEvent,
    TaskEventListResponse,
    SyncValidationReport,
    ShutterAction,
    UpdateCameraRequest,
)
from .service import CameraControlService
from .task_events import TaskEventConflictError, TaskEventStore
from .sync_validation import SyncValidationAnalyzer

data_dir = Path(os.getenv("GOPRO_DATA_DIR", ".data"))
adapter = CohnCameraAdapter(
    data_dir / "cameras.json",
    scan_cidrs=os.getenv("GOPRO_SCAN_CIDRS", "192.168.1.0/24"),
    preview_port_start=int(os.getenv("GOPRO_PREVIEW_PORT_START", "8554")),
    credentials_path=Path(os.environ["GOPRO_CREDENTIALS_FILE"])
    if os.getenv("GOPRO_CREDENTIALS_FILE")
    else None,
)
service = CameraControlService(adapter)
task_event_store = TaskEventStore(data_dir / "task_events.json")
capture_session_store = CaptureSessionStore(
    Path(os.getenv("GOPRO_CAPTURE_DIR", data_dir / "sessions")),
    adapter,
    finalize_delay=float(os.getenv("GOPRO_MEDIA_FINALIZE_DELAY_SECONDS", "15")),
)
sync_validation_analyzer = SyncValidationAnalyzer()

app = FastAPI(title="GoPro 多机控制 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:15173", "http://127.0.0.1:15173"],
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


@app.post("/api/cameras/apply-recording-config", response_model=BatchCommandResponse)
async def apply_recording_config(request: CameraSelection) -> BatchCommandResponse:
    return await service.apply_recording_config(request.camera_ids)


@app.get("/api/recording-config", response_model=RecordingConfig)
async def get_recording_config() -> RecordingConfig:
    try:
        return adapter.get_recording_config()
    except CameraRegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/recording-config", response_model=RecordingConfig)
async def update_recording_config(request: RecordingConfig) -> RecordingConfig:
    try:
        return await adapter.update_recording_config(request)
    except CameraRegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cameras/discover", response_model=DiscoveryResponse)
async def discover_cameras(request: DiscoverCameraRequest) -> DiscoveryResponse:
    try:
        return await adapter.discover(request)
    except CameraRegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cameras/{camera_id}/locate", response_model=CameraStatus)
async def locate_camera(camera_id: str) -> CameraStatus:
    try:
        return await adapter.locate(camera_id)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="设备不存在") from exc
    except CameraUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cameras/{camera_id}/thumbnail")
async def latest_thumbnail(camera_id: str) -> Response:
    try:
        content, media_type = await adapter.latest_thumbnail(camera_id)
        return Response(content=content, media_type=media_type, headers={"Cache-Control": "no-store"})
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="设备不存在") from exc
    except CameraUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/cameras/{camera_id}/monitor-stream")
async def monitor_stream(camera_id: str) -> StreamingResponse:
    try:
        frames = await adapter.open_monitor_stream(camera_id)
        return StreamingResponse(
            frames,
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="设备不存在") from exc
    except CameraUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_camera(camera_id: str) -> Response:
    try:
        await adapter.remove(camera_id)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="设备不存在") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/api/cameras/{camera_id}", response_model=CameraStatus)
async def update_camera(camera_id: str, request: UpdateCameraRequest) -> CameraStatus:
    try:
        return await adapter.update(camera_id, request)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail="设备不存在") from exc


@app.get("/api/task-events", response_model=TaskEventListResponse)
async def list_task_events() -> TaskEventListResponse:
    return await task_event_store.list_events()


@app.post("/api/task-events", response_model=TaskEvent, status_code=status.HTTP_201_CREATED)
async def create_task_event(request: CreateTaskEventRequest) -> TaskEvent:
    try:
        return await task_event_store.create(request)
    except TaskEventConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/capture-sessions/start", response_model=CaptureSession, status_code=status.HTTP_201_CREATED)
async def start_capture_session(request: CaptureSessionRequest) -> CaptureSession:
    try:
        session = await capture_session_store.begin(request.camera_ids)
        await task_event_store.clear()
        result = await service.set_shutter(request.camera_ids, ShutterAction.START)
        errors = [item.message for item in result.results if not item.success]
        if errors:
            await capture_session_store.add_errors(session.id, errors)
        return await capture_session_store.get(session.id)
    except (CameraUnavailableError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/capture-sessions/{session_id}/stop-and-collect", response_model=CaptureSession)
async def stop_and_collect_capture_session(session_id: str) -> CaptureSession:
    try:
        session = await capture_session_store.get(session_id)
        result = await service.set_shutter(session.camera_ids, ShutterAction.STOP)
        errors = [item.message for item in result.results if not item.success]
        if errors:
            await capture_session_store.add_errors(session.id, errors)
        task_events = await task_event_store.list_events()
        return await capture_session_store.start_collection(session_id, task_events)
    except CaptureSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="采集会话不存在") from exc


@app.get("/api/capture-sessions/{session_id}", response_model=CaptureSession)
async def get_capture_session(session_id: str) -> CaptureSession:
    try:
        return await capture_session_store.get(session_id)
    except CaptureSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="采集会话不存在") from exc


@app.post("/api/capture-sessions/{session_id}/cancel-collection", response_model=CaptureSession)
async def cancel_capture_collection(session_id: str) -> CaptureSession:
    try:
        return await capture_session_store.cancel_collection(session_id)
    except CaptureSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="采集会话不存在") from exc


@app.post("/api/capture-sessions/{session_id}/sync-validation", response_model=SyncValidationReport)
async def analyze_sync_validation(session_id: str) -> SyncValidationReport:
    try:
        session = await capture_session_store.get(session_id)
        if session.status not in {"complete", "partial"}:
            raise HTTPException(status_code=409, detail="请等待素材收集完成后再分析")
        report = await sync_validation_analyzer.analyze(
            session,
            capture_session_store._session_dir(session_id),
        )
        report_path = capture_session_store._session_dir(session_id) / "sync_validation.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report
    except CaptureSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="采集会话不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
