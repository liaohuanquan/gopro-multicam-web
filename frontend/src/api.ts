import type { BatchCommandResponse, CameraStatus } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
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

export function markTimecodeSynced(cameraIds: string[]): Promise<BatchCommandResponse> {
  return request("/api/cameras/timecode-synced", {
    method: "POST",
    body: JSON.stringify({ camera_ids: cameraIds }),
  });
}

