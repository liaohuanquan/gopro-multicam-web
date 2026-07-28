import { useEffect, useRef, useState } from "react";
import { FolderKanban, Square, X } from "lucide-react";
import type { CaptureSession } from "../types";

export interface ControlDockProps {
  cameraCount: number;
  explicitlySelected: boolean;
  startDisabled: boolean;
  stopDisabled: boolean;
  session: CaptureSession | undefined;
  onStart: () => void;
  onStop: () => void;
  onCancel: () => void;
  onOpenProjects: () => void;
}

function formatBytes(value: number) {
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(0)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function formatRate(value: number) {
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(0)} KB/s`;
  return `${(value / 1024 ** 2).toFixed(1)} MB/s`;
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "--";
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${Math.ceil(seconds % 60)} 秒`;
}

export function ControlDock({ cameraCount, explicitlySelected, startDisabled, stopDisabled, session, onStart, onStop, onCancel, onOpenProjects }: ControlDockProps) {
  const sampleRef = useRef({ sessionId: "", bytes: 0, time: performance.now() });
  const [downloadRate, setDownloadRate] = useState(0);
  const collecting = session?.status === "collecting";
  const finalizing = collecting && session.files_total === 0 && session.bytes_total === 0;
  const clipping = collecting && session.files_total > 0 && session.files_completed === session.files_total && session.clips_total > 0;
  const composing = clipping && session.clips_completed === session.clips_total && session.grids_total > 0;
  const complete = session?.status === "complete" || session?.status === "partial";
  const collected = session?.status === "collected";
  const partial = session?.status === "partial" || session?.status === "collection_failed";
  const cancelled = session?.status === "cancelled";
  const downloadProgress = session?.bytes_total ? Math.min(100, session.bytes_downloaded / session.bytes_total * 100) : 0;
  const remainingSeconds = downloadRate > 0 && session
    ? (session.bytes_total - session.bytes_downloaded) / downloadRate
    : Number.NaN;

  useEffect(() => {
    if (!session || !collecting || clipping) {
      setDownloadRate(0);
      return;
    }
    const now = performance.now();
    const previous = sampleRef.current;
    if (previous.sessionId !== session.id || session.bytes_downloaded < previous.bytes) {
      sampleRef.current = { sessionId: session.id, bytes: session.bytes_downloaded, time: now };
      setDownloadRate(0);
      return;
    }
    const elapsed = (now - previous.time) / 1000;
    const bytes = session.bytes_downloaded - previous.bytes;
    if (elapsed >= 0.5 && bytes > 0) {
      const currentRate = bytes / elapsed;
      setDownloadRate((oldRate) => oldRate ? oldRate * 0.65 + currentRate * 0.35 : currentRate);
      sampleRef.current = { sessionId: session.id, bytes: session.bytes_downloaded, time: now };
    }
  }, [session?.id, session?.bytes_downloaded, collecting, clipping]);

  return (
    <footer className="control-dock">
      <div className="dock-status">
        <strong>{composing ? `正在生成宫格 ${session.grids_completed}/${session.grids_total}` : clipping ? `正在切片 ${session.clips_completed}/${session.clips_total}` : finalizing ? "等待相机完成编码" : collecting ? `正在收集 ${session.files_completed}/${session.files_total}` : collected ? "素材已回收 · 等待生成切片" : cancelled ? "本次收集已中断" : partial ? "收集或处理不完整" : complete ? `已完成 · ${session.clips_completed} 个机位片段` : `${cameraCount} 台相机`}</strong>
        <span>{clipping ? session.id : finalizing ? "停止录制后等待 15 秒，再读取相机素材" : collecting ? `${formatBytes(session.bytes_downloaded)} / ${formatBytes(session.bytes_total)} · ${downloadProgress.toFixed(1)}% · ${downloadRate ? formatRate(downloadRate) : "测速中"} · 剩余 ${formatTime(remainingSeconds)}` : collected ? `${session.id} · 前往项目页面手动处理` : cancelled ? `已保留 ${session.files_completed} 个完整文件` : partial ? session?.errors[0] : complete ? session?.id : explicitlySelected ? "已选择设备" : "默认控制全部设备"}</span>
        {collecting && !clipping && !finalizing && <div className="dock-progress" role="progressbar" aria-valuenow={downloadProgress} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${downloadProgress}%` }} /></div>}
      </div>
      <div className="dock-actions">
        {collected
          ? <button className="button secondary" onClick={onOpenProjects}><FolderKanban size={17} /> 打开项目</button>
          : collecting
          ? <button className="button stop" onClick={onCancel}><X size={17} /> 中断收集</button>
          : <button className="button stop" disabled={stopDisabled} onClick={onStop}><Square size={17} fill="currentColor" /> 结束录制</button>}
        <button className="button start" disabled={startDisabled} onClick={onStart}><span className="rec-dot" /> 开始录制</button>
      </div>
    </footer>
  );
}
