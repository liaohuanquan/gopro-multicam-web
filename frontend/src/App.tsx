import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BatteryMedium,
  Camera,
  Check,
  Clock3,
  ExternalLink,
  HardDrive,
  Radio,
  RefreshCw,
  Square,
  Thermometer,
  Video,
  Wifi,
  WifiOff,
} from "lucide-react";
import { toast } from "sonner";

import { getCameras, markTimecodeSynced, setShutter } from "./api";
import { formatDuration, formatSyncAge } from "./format";
import type { BatchCommandResponse, CameraStatus } from "./types";

const TIMECODE_URL = "https://gopro.github.io/labs/control/precisiontime_utc/";

function CameraCard({
  camera,
  selected,
  onToggle,
}: {
  camera: CameraStatus;
  selected: boolean;
  onToggle: () => void;
}) {
  const ready = camera.online && camera.battery_percent >= 20 && camera.sd_remaining_minutes >= 10;
  return (
    <article className={`camera-card ${selected ? "selected" : ""} ${camera.recording ? "recording" : ""}`}>
      <button className="card-select" onClick={onToggle} aria-label={`选择 ${camera.name}`}>
        <span className={`checkbox ${selected ? "checked" : ""}`}>{selected && <Check size={14} />}</span>
      </button>

      <div className="camera-heading">
        <div className="camera-icon"><Camera size={22} /></div>
        <div>
          <h3>{camera.name}</h3>
          <p>{camera.location}</p>
        </div>
        <span className={`status-dot ${camera.online ? "online" : "offline"}`}>
          {camera.online ? <Wifi size={14} /> : <WifiOff size={14} />}
          {camera.online ? "在线" : "离线"}
        </span>
      </div>

      <div className={`recording-panel ${camera.recording ? "active" : ""}`}>
        <span className="recording-light" />
        <div>
          <span>{camera.recording ? "REC" : "待机"}</span>
          <strong>{camera.recording ? formatDuration(camera.recording_seconds) : "--:--:--"}</strong>
        </div>
      </div>

      <dl className="camera-metrics">
        <div><dt><BatteryMedium size={16} /> 电量</dt><dd>{camera.battery_percent}%</dd></div>
        <div><dt><HardDrive size={16} /> 可录制</dt><dd>{camera.sd_remaining_minutes} 分钟</dd></div>
        <div><dt><Thermometer size={16} /> 温度</dt><dd>{camera.temperature_c.toFixed(1)}°C</dd></div>
        <div><dt><Clock3 size={16} /> 时间码</dt><dd className={camera.timecode_synced_at ? "sync-ok" : "sync-missing"}>{formatSyncAge(camera.timecode_synced_at)}</dd></div>
      </dl>

      <div className="camera-footer">
        <span>{camera.mode}</span>
        <span className={ready ? "ready" : "not-ready"}>{ready ? "拍摄就绪" : "需要检查"}</span>
      </div>
    </article>
  );
}

function summarizeResult(result: BatchCommandResponse, successText: string) {
  if (result.failure_count === 0) {
    toast.success(`${result.success_count} 台相机${successText}`);
    return;
  }
  toast.error(`${result.success_count} 台成功，${result.failure_count} 台失败`, {
    description: result.results.filter((item) => !item.success).map((item) => item.message).join("；"),
  });
}

export default function App() {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 1000,
  });
  const cameras = camerasQuery.data ?? [];
  const effectiveSelectedIds = selectedIds.length ? selectedIds : cameras.map((camera) => camera.id);

  const shutterMutation = useMutation({
    mutationFn: ({ action, ids }: { action: "start" | "stop"; ids: string[] }) => setShutter(ids, action),
    onSuccess: (result, variables) => {
      summarizeResult(result, variables.action === "start" ? "已开始录制" : "已停止录制");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("控制命令发送失败", { description: error.message }),
  });

  const timecodeMutation = useMutation({
    mutationFn: markTimecodeSynced,
    onSuccess: (result) => {
      summarizeResult(result, "已记录时间码同步");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("同步记录失败", { description: error.message }),
  });

  const summary = useMemo(() => ({
    online: cameras.filter((camera) => camera.online).length,
    recording: cameras.filter((camera) => camera.recording).length,
    synced: cameras.filter((camera) => camera.timecode_synced_at).length,
    ready: cameras.filter((camera) => camera.online && camera.battery_percent >= 20 && camera.sd_remaining_minutes >= 10).length,
  }), [cameras]);

  function toggleCamera(id: string) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  const pending = shutterMutation.isPending || timecodeMutation.isPending;

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Video size={24} /></div>
          <div><h1>GoPro 多机控制台</h1><p>Ego4D · HERO13 四机采集</p></div>
        </div>
        <div className="mock-badge"><Radio size={15} /> 模拟设备模式</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">CAPTURE CONTROL</p>
          <h2>四个视角，一次控制。</h2>
          <p>拍摄前同步时间码，检查全部设备，然后统一开始录制。</p>
        </div>
        <div className="summary-grid">
          <div><span>{summary.online}/4</span><small>设备在线</small></div>
          <div><span>{summary.ready}/4</span><small>拍摄就绪</small></div>
          <div><span>{summary.synced}/4</span><small>时间码同步</small></div>
          <div className={summary.recording ? "summary-recording" : ""}><span>{summary.recording}/4</span><small>正在录制</small></div>
        </div>
      </section>

      <section className="workflow-panel">
        <div className="workflow-copy">
          <span className="step-number">01</span>
          <div><h3>同步 UTC 时间码</h3><p>在新页面显示动态二维码，让四台相机依次扫码；完成后返回记录同步时间。</p></div>
        </div>
        <div className="workflow-actions">
          <a className="button secondary" href={TIMECODE_URL} target="_blank" rel="noreferrer">
            打开动态二维码 <ExternalLink size={17} />
          </a>
          <button className="button ghost" disabled={pending || !cameras.length} onClick={() => timecodeMutation.mutate(effectiveSelectedIds)}>
            <Check size={17} /> 已完成同步
          </button>
        </div>
      </section>

      <section className="camera-section">
        <div className="section-heading">
          <div><p className="eyebrow">CAMERAS</p><h2>设备状态</h2></div>
          <div className="selection-controls">
            <button onClick={() => setSelectedIds(cameras.map((camera) => camera.id))}>全选</button>
            <button onClick={() => setSelectedIds([])}>默认全部</button>
            <button aria-label="刷新" onClick={() => camerasQuery.refetch()}><RefreshCw size={16} /></button>
          </div>
        </div>

        {camerasQuery.isError ? (
          <div className="error-state">无法连接本地控制服务，请确认后端已启动。</div>
        ) : (
          <div className="camera-grid">
            {cameras.map((camera) => <CameraCard key={camera.id} camera={camera} selected={effectiveSelectedIds.includes(camera.id)} onToggle={() => toggleCamera(camera.id)} />)}
          </div>
        )}
      </section>

      <footer className="control-dock">
        <div>
          <strong>{effectiveSelectedIds.length} 台相机</strong>
          <span>{selectedIds.length ? "已选择设备" : "默认控制全部设备"}</span>
        </div>
        <div className="dock-actions">
          <button className="button stop" disabled={pending || !cameras.length} onClick={() => shutterMutation.mutate({ action: "stop", ids: effectiveSelectedIds })}>
            <Square size={17} fill="currentColor" /> 全部停止
          </button>
          <button className="button start" disabled={pending || !cameras.length} onClick={() => shutterMutation.mutate({ action: "start", ids: effectiveSelectedIds })}>
            <span className="rec-dot" /> 全部开始录制
          </button>
        </div>
      </footer>
    </main>
  );
}

