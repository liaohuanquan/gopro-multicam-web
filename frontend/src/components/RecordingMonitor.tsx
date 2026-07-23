import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";

import type { CameraStatus } from "../types";

export function RecordingMonitor({ camera }: { camera: CameraStatus }) {
  const [retryCount, setRetryCount] = useState(0);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    setAvailable(false);
    setRetryCount(0);
  }, [camera.id, camera.online, camera.recording]);

  const placeholder = !camera.online
    ? "设备离线"
    : camera.recording
      ? "正在连接录制监看…"
      : "开始录制后显示实时监看";

  return (
    <div className="recent-frame">
      {camera.online && camera.recording && (
        <img
          key={`${camera.id}-${retryCount}`}
          src={`/api/cameras/${encodeURIComponent(camera.id)}/monitor-stream?retry=${retryCount}`}
          onLoad={() => setAvailable(true)}
          onError={() => {
            setAvailable(false);
            window.setTimeout(() => setRetryCount((value) => value + 1), 1000);
          }}
          alt={`${camera.name} 录制监看`}
        />
      )}
      {(!camera.online || !camera.recording || !available) && (
        <div className="frame-placeholder"><ImageOff size={20} /><span>{placeholder}</span></div>
      )}
      <span className="frame-label">实时录制监看</span>
      {camera.latency_ms !== null && (
        <span className={`latency-badge ${camera.latency_ms < 60 ? "good" : camera.latency_ms < 120 ? "medium" : "poor"}`}>
          {camera.latency_ms} ms
        </span>
      )}
    </div>
  );
}
