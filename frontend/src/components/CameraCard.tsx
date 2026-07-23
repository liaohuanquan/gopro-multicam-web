import { BatteryMedium, Camera, Check, Flame, HardDrive, Pencil, Trash2, Volume2, Wifi, WifiOff } from "lucide-react";

import { formatDuration } from "../format";
import type { CameraStatus } from "../types";
import { RecordingMonitor } from "./RecordingMonitor";

export interface CameraCardProps {
  camera: CameraStatus;
  selected: boolean;
  onToggle: () => void;
  onRemove: () => void;
  onLocate: () => void;
  onRename: () => void;
}

export function CameraCard({ camera, selected, onToggle, onRemove, onLocate, onRename }: CameraCardProps) {
  const ready = camera.online
    && (camera.battery_percent === null || camera.battery_percent >= 20)
    && (camera.sd_remaining_minutes === null || camera.sd_remaining_minutes >= 10)
    && camera.overheating !== true;

  return (
    <article className={`camera-card ${selected ? "selected" : ""} ${camera.recording ? "recording" : ""}`}>
      <div className="camera-heading">
        <div className="camera-icon"><Camera size={22} /></div>
        <div><h3>{camera.name}</h3><p>{camera.location}</p></div>
        <div className="camera-actions">
          <span className={`status-dot ${camera.online ? "online" : "offline"}`}>
            {camera.online ? <Wifi size={14} /> : <WifiOff size={14} />}{camera.online ? "在线" : "离线"}
          </span>
          <button className="rename-camera" onClick={onRename} title="修改设备名称" aria-label={`修改 ${camera.name} 名称`}><Pencil size={15} /></button>
          <button className="locate-camera" disabled={!camera.online} onClick={onLocate} title="让相机发出声音" aria-label={`定位 ${camera.name}`}><Volume2 size={15} /></button>
          <button className="remove-camera" onClick={onRemove} aria-label={`移除 ${camera.name}`}><Trash2 size={15} /></button>
          <button className={`camera-checkbox ${selected ? "checked" : ""}`} onClick={onToggle} aria-label={`选择 ${camera.name}`} aria-pressed={selected}>{selected && <Check size={14} />}</button>
        </div>
      </div>

      <RecordingMonitor camera={camera} />

      <div className={`recording-panel ${camera.recording ? "active" : ""}`}>
        <span className="recording-light" />
        <div><span>{camera.recording ? "REC" : "待机"}</span><strong>{camera.recording ? formatDuration(camera.recording_seconds) : "--:--:--"}</strong></div>
      </div>

      <dl className="camera-metrics">
        <div><dt><BatteryMedium size={16} /> 电量</dt><dd>{camera.battery_percent === null ? "--" : `${camera.battery_percent}%`}</dd></div>
        <div><dt><HardDrive size={16} /> 可录制</dt><dd>{camera.sd_remaining_minutes === null ? "--" : `${camera.sd_remaining_minutes} 分钟`}{camera.sd_remaining_gb !== null ? ` · ${camera.sd_remaining_gb} GB` : ""}</dd></div>
        <div><dt><Flame size={16} /> 温度状态</dt><dd className={camera.overheating ? "sync-missing" : "sync-ok"}>{camera.overheating === null ? "--" : camera.overheating ? "过热" : "正常"}</dd></div>
      </dl>

      <div className="camera-footer"><span>{camera.mode}</span><span className={ready ? "ready" : "not-ready"}>{ready ? "拍摄就绪" : "需要检查"}</span></div>
    </article>
  );
}
