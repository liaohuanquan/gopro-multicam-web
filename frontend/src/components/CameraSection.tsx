import { Camera, Plus, RefreshCw, ScanLine, SlidersHorizontal } from "lucide-react";

import type { CameraStatus } from "../types";
import { CameraCard } from "./CameraCard";

export interface CameraSectionProps {
  cameras: CameraStatus[];
  selectedIds: string[];
  loadingError: boolean;
  onAddCamera: () => void;
  onSelectAll: () => void;
  onRefresh: () => void;
  onOpenRecordingConfig: () => void;
  onOpenSyncValidation: () => void;
  applyDisabled: boolean;
  onToggle: (cameraId: string) => void;
  onLocate: (cameraId: string) => void;
  onRename: (camera: CameraStatus) => void;
  onRemove: (camera: CameraStatus) => void;
}

export function CameraSection({ cameras, selectedIds, loadingError, onAddCamera, onSelectAll, onRefresh, onOpenRecordingConfig, onOpenSyncValidation, applyDisabled, onToggle, onLocate, onRename, onRemove }: CameraSectionProps) {
  return (
    <section className="camera-section">
      <div className="section-heading">
        <div><h2>相机</h2></div>
        <div className="selection-controls">
          <button className="add-inline" onClick={onAddCamera}><Plus size={16} /> 添加设备</button>
          <button disabled={applyDisabled} onClick={onOpenRecordingConfig}><SlidersHorizontal size={16} /> 录制参数</button>
          <button disabled={applyDisabled || selectedIds.length < 2} onClick={onOpenSyncValidation}><ScanLine size={16} /> 同步验证</button>
          <button onClick={onSelectAll}>全选</button>
          <button aria-label="刷新" onClick={onRefresh}><RefreshCw size={16} /></button>
        </div>
      </div>

      {loadingError ? (
        <div className="error-state">无法连接本地控制服务，请确认后端已启动。</div>
      ) : cameras.length === 0 ? (
        <div className="empty-state">
          <div><Camera size={30} /></div>
          <h3>设备组还是空的</h3>
          <p>生成 GoPro Labs 二维码，让 HERO13 扫码加入采集网络并应用统一录制参数。</p>
          <button className="button secondary" onClick={onAddCamera}><Plus size={17} />扫码添加第一台相机</button>
        </div>
      ) : (
        <div className="camera-grid">
          {cameras.map((camera) => (
            <CameraCard
              key={camera.id}
              camera={camera}
              selected={selectedIds.includes(camera.id)}
              onToggle={() => onToggle(camera.id)}
              onLocate={() => onLocate(camera.id)}
              onRename={() => onRename(camera)}
              onRemove={() => onRemove(camera)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
