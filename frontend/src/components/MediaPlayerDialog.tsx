import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Clock3, FileVideo, Folder, FolderOpen, LoaderCircle, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { getCaptureSessionMedia, getCaptureSessionMediaUrl } from "../api";
import type { CaptureSession, SessionMediaAsset } from "../types";

function formatBytes(value: number) {
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

function formatDuration(value: number) {
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  const seconds = Math.floor(value % 60);
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

function parseTimecode(value: string, fps: number) {
  const parts = value.match(/^(\d{2}):(\d{2}):(\d{2})([:;])(\d{2})$/);
  if (!parts) return null;
  const nominal = Math.round(fps);
  const [, hh, mm, ss, separator, ff] = parts;
  const totalMinutes = Number(hh) * 60 + Number(mm);
  const dropFrames = separator === ";" ? Math.round(nominal * 0.066666) : 0;
  const frame = ((Number(hh) * 3600 + Number(mm) * 60 + Number(ss)) * nominal + Number(ff))
    - dropFrames * (totalMinutes - Math.floor(totalMinutes / 10));
  return { frame, nominal, dropFrames, separator };
}

function frameToTimecode(frame: number, nominal: number, dropFrames: number, separator: string) {
  let adjusted = Math.max(0, frame);
  if (dropFrames) {
    const framesPer10Minutes = nominal * 600 - dropFrames * 9;
    const framesPerMinute = nominal * 60 - dropFrames;
    const tenMinuteBlocks = Math.floor(adjusted / framesPer10Minutes);
    const remainder = adjusted % framesPer10Minutes;
    adjusted += dropFrames * 9 * tenMinuteBlocks;
    if (remainder >= dropFrames) adjusted += dropFrames * Math.floor((remainder - dropFrames) / framesPerMinute);
  }
  adjusted %= nominal * 3600 * 24;
  const ff = adjusted % nominal;
  const totalSeconds = Math.floor(adjusted / nominal);
  const ss = totalSeconds % 60;
  const mm = Math.floor(totalSeconds / 60) % 60;
  const hh = Math.floor(totalSeconds / 3600);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}${separator}${String(ff).padStart(2, "0")}`;
}

function liveTimecode(asset: SessionMediaAsset, mediaTime: number) {
  if (!asset.timecode) return null;
  const parsed = parseTimecode(asset.timecode, asset.fps);
  if (!parsed) return null;
  return frameToTimecode(parsed.frame + Math.floor(mediaTime * asset.fps), parsed.nominal, parsed.dropFrames, parsed.separator);
}

interface MediaFolderNode {
  name: string;
  path: string;
  folders: Map<string, MediaFolderNode>;
  files: SessionMediaAsset[];
}

function buildMediaTree(assets: SessionMediaAsset[]): MediaFolderNode {
  const root: MediaFolderNode = { name: "", path: "", folders: new Map(), files: [] };
  for (const asset of assets) {
    const parts = asset.path.split("/");
    let current = root;
    for (const part of parts.slice(0, -1)) {
      const path = current.path ? `${current.path}/${part}` : part;
      if (!current.folders.has(part)) current.folders.set(part, { name: part, path, folders: new Map(), files: [] });
      current = current.folders.get(part)!;
    }
    current.files.push(asset);
  }
  return root;
}

function folderLabel(name: string) {
  if (name === "source") return "原始素材";
  if (name === "clips") return "切片结果";
  if (/^task_\d+$/.test(name)) return name.replace("task_", "任务 ");
  return name;
}

function MediaTree({ node, selectedPath, onSelect, depth = 0 }: { node: MediaFolderNode; selectedPath: string; onSelect: (path: string) => void; depth?: number }) {
  const folders = [...node.folders.values()].sort((left, right) => {
    const order = { source: 0, clips: 1 } as Record<string, number>;
    return (order[left.name] ?? 2) - (order[right.name] ?? 2) || left.name.localeCompare(right.name);
  });
  return <>
    {folders.map((folder) => <details className="media-tree-folder" open key={folder.path}>
      <summary style={{ paddingLeft: 8 + depth * 13 }}><ChevronRight size={13} className="tree-chevron" /><Folder size={14} className="folder-closed" /><FolderOpen size={14} className="folder-open" /><strong>{folderLabel(folder.name)}</strong></summary>
      <div>
        <MediaTree node={folder} selectedPath={selectedPath} onSelect={onSelect} depth={depth + 1} />
      </div>
    </details>)}
    {[...node.files].sort((left, right) => left.name.localeCompare(right.name)).map((asset) => <button key={asset.path} className={`media-tree-file ${asset.path === selectedPath ? "active" : ""}`} style={{ paddingLeft: 28 + depth * 13 }} onClick={() => onSelect(asset.path)}>
      <FileVideo size={14} />
      <span><strong>{asset.name}</strong><small>{formatBytes(asset.size_bytes)}</small></span>
    </button>)}
  </>;
}

function VideoStage({ sessionId, asset }: { sessionId: string; asset: SessionMediaAsset }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [mediaTime, setMediaTime] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let callbackId = 0;
    const update = (_now: number, metadata: VideoFrameCallbackMetadata) => {
      setMediaTime(metadata.mediaTime);
      callbackId = video.requestVideoFrameCallback(update);
    };
    callbackId = video.requestVideoFrameCallback(update);
    return () => video.cancelVideoFrameCallback(callbackId);
  }, [asset.path]);

  const timecode = liveTimecode(asset, mediaTime);
  const frame = Math.floor(mediaTime * asset.fps);
  return <>
    <div className="media-video-stage">
      <video ref={videoRef} key={asset.path} src={getCaptureSessionMediaUrl(sessionId, asset.path)} controls preload="metadata" />
      <div className="media-timecode-overlay">
        <span>{timecode ? "TIMECODE" : "MEDIA TIME"}</span>
        <strong>{timecode ?? formatDuration(mediaTime)}</strong>
        <small>FRAME {String(frame).padStart(6, "0")}</small>
      </div>
    </div>
    <div className="media-info-grid">
      <div><span>分辨率</span><strong>{asset.width} × {asset.height}</strong></div>
      <div><span>帧率</span><strong>{asset.fps.toFixed(3)} FPS</strong></div>
      <div><span>时长</span><strong>{formatDuration(asset.duration_seconds)}</strong></div>
      <div><span>编码</span><strong>{asset.codec.toUpperCase()}</strong></div>
      <div><span>文件大小</span><strong>{formatBytes(asset.size_bytes)}</strong></div>
      <div><span>起始时间码</span><strong>{asset.timecode ?? "无内嵌时间码"}</strong></div>
    </div>
  </>;
}

export function MediaPlayerDialog({ session, onClose }: { session: CaptureSession; onClose: () => void }) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const mediaQuery = useQuery({
    queryKey: ["capture-session-media", session.id],
    queryFn: () => getCaptureSessionMedia(session.id),
  });
  const assets = mediaQuery.data ?? [];
  const selected = useMemo(() => assets.find((item) => item.path === selectedPath) ?? assets[0], [assets, selectedPath]);
  const mediaTree = useMemo(() => buildMediaTree(assets), [assets]);

  return <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="media-player-dialog" role="dialog" aria-modal="true" aria-label={`${session.id} 素材`}>
      <header className="dialog-header">
        <div><span>SESSION MEDIA</span><h2>查看素材</h2><p>{session.id}</p></div>
        <button onClick={onClose} aria-label="关闭"><X /></button>
      </header>
      {mediaQuery.isLoading && <div className="media-loading"><LoaderCircle className="spin" />正在读取视频信息</div>}
      {mediaQuery.isError && <div className="media-loading error-state">素材信息读取失败</div>}
      {!mediaQuery.isLoading && assets.length === 0 && <div className="media-loading">当前 Session 没有可播放的视频</div>}
      {selected && <div className="media-browser">
        <aside className="media-list">
          <MediaTree node={mediaTree} selectedPath={selected.path} onSelect={setSelectedPath} />
        </aside>
        <main className="media-player-main">
          <div className="media-player-title"><div><Clock3 size={16} /><strong>{selected.camera_name}</strong><span>{selected.path}</span></div></div>
          <VideoStage sessionId={session.id} asset={selected} />
        </main>
      </div>}
    </section>
  </div>;
}
