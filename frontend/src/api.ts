import type { BatchCommandResponse, CameraStatus, CaptureSession, CreateTaskEventInput, DiscoverCameraInput, DiscoveryResponse, NetworkConfig, RecordingConfig, RecordingPreset, SessionMediaAsset, SyncValidationReport, TaskEvent, TaskEventListResponse } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getCameras(): Promise<CameraStatus[]> {
  return request("/api/cameras");
}

export function setShutter(
  cameraIds: string[],
  action: "start" | "stop",
): Promise<BatchCommandResponse> {
  return request("/api/cameras/shutter", {
    method: "POST",
    body: JSON.stringify({ camera_ids: cameraIds, action }),
  });
}

export function applyRecordingConfig(cameraIds: string[]): Promise<BatchCommandResponse> {
  return request("/api/cameras/apply-recording-config", {
    method: "POST",
    body: JSON.stringify({ camera_ids: cameraIds }),
  });
}

export function getRecordingConfig(): Promise<RecordingConfig> {
  return request("/api/recording-config");
}

export function updateRecordingConfig(config: RecordingConfig): Promise<RecordingConfig> {
  return request("/api/recording-config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function getRecordingPresets(): Promise<RecordingPreset[]> {
  return request("/api/recording-presets");
}

export function getNetworkConfig(): Promise<NetworkConfig> {
  return request("/api/config/network");
}

export function updateNetworkConfig(config: NetworkConfig): Promise<NetworkConfig> {
  return request("/api/config/network", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export function saveRecordingPreset(name: string, config: RecordingConfig): Promise<RecordingPreset> {
  return request("/api/recording-presets", {
    method: "PUT",
    body: JSON.stringify({ name, config }),
  });
}

export async function deleteRecordingPreset(name: string): Promise<void> {
  const response = await fetch(`/api/recording-presets/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `删除失败：${response.status}`);
  }
}

export function discoverCameras(input: DiscoverCameraInput): Promise<DiscoveryResponse> {
  return request("/api/cameras/discover", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function locateCamera(cameraId: string): Promise<CameraStatus> {
  return request(`/api/cameras/${encodeURIComponent(cameraId)}/locate`, { method: "POST" });
}

export function renameCamera(cameraId: string, name: string): Promise<CameraStatus> {
  return request(`/api/cameras/${encodeURIComponent(cameraId)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function removeCamera(cameraId: string): Promise<void> {
  const response = await fetch(`/api/cameras/${encodeURIComponent(cameraId)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`移除失败：${response.status}`);
}

export function getTaskEvents(): Promise<TaskEventListResponse> {
  return request("/api/task-events");
}

export function createTaskEvent(input: CreateTaskEventInput): Promise<TaskEvent> {
  return request("/api/task-events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function startCaptureSession(cameraIds: string[]): Promise<CaptureSession> {
  return request("/api/capture-sessions/start", {
    method: "POST",
    body: JSON.stringify({ camera_ids: cameraIds }),
  });
}

export function stopAndCollectCaptureSession(sessionId: string): Promise<CaptureSession> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}/stop-and-collect`, { method: "POST" });
}

export function getCaptureSession(sessionId: string): Promise<CaptureSession> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}`);
}

export function getCaptureSessions(): Promise<CaptureSession[]> {
  return request("/api/capture-sessions");
}

export function getCaptureSessionMedia(sessionId: string): Promise<SessionMediaAsset[]> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}/media`);
}

export function getCaptureSessionMediaUrl(sessionId: string, path: string): string {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `/api/capture-sessions/${encodeURIComponent(sessionId)}/media-file/${encodedPath}`;
}

export function processCaptureSession(sessionId: string): Promise<CaptureSession> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}/process`, { method: "POST" });
}

export function cancelCaptureCollection(sessionId: string): Promise<CaptureSession> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}/cancel-collection`, { method: "POST" });
}

export function analyzeSyncValidation(sessionId: string): Promise<SyncValidationReport> {
  return request(`/api/capture-sessions/${encodeURIComponent(sessionId)}/sync-validation`, { method: "POST" });
}
