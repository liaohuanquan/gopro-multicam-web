import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, FolderKanban, LoaderCircle, Play, RefreshCw, Video } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { getCaptureSessions, processCaptureSession } from "../api";
import type { CaptureSession } from "../types";
import { MediaPlayerDialog } from "./MediaPlayerDialog";

const statusText: Record<CaptureSession["status"], string> = {
  recording: "录制中",
  collecting: "回收素材中",
  collected: "待生成切片",
  processing: "正在生成切片",
  complete: "处理完成",
  partial: "素材不完整",
  collection_failed: "回收失败",
  process_failed: "处理失败",
  cancelled: "回收已中断",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(new Date(value));
}

function formatBytes(value: number) {
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(0)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

export function SessionsPage() {
  const [mediaSession, setMediaSession] = useState<CaptureSession | null>(null);
  const queryClient = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: ["capture-sessions"],
    queryFn: getCaptureSessions,
    refetchInterval: (query) => query.state.data?.some((item) => ["collecting", "processing"].includes(item.status)) ? 1000 : 5000,
  });
  const processMutation = useMutation({
    mutationFn: processCaptureSession,
    onSuccess: (session) => {
      toast.success("切片任务已启动", { description: session.id });
      queryClient.invalidateQueries({ queryKey: ["capture-sessions"] });
    },
    onError: (error: Error) => toast.error("切片任务启动失败", { description: error.message }),
  });
  const sessions = sessionsQuery.data ?? [];

  return (
    <div className="projects-page">
      <header className="workspace-header">
        <div><h2>采集项目</h2><span>每次回收形成一个独立 Session，确认素材后手动生成切片</span></div>
        <button className="button ghost" onClick={() => void sessionsQuery.refetch()}><RefreshCw size={16} />刷新</button>
      </header>

      <section className="project-list">
        {sessionsQuery.isLoading && <div className="empty-state"><LoaderCircle className="spin" /><h3>正在读取 Session</h3></div>}
        {sessionsQuery.isError && <div className="error-state">Session 列表读取失败</div>}
        {!sessionsQuery.isLoading && sessions.length === 0 && (
          <div className="empty-state"><div><FolderKanban /></div><h3>还没有采集项目</h3><p>结束一次录制并完成素材回收后，Session 会出现在这里。</p></div>
        )}
        {sessions.map((session) => {
          const processing = session.status === "processing";
          const canProcess = ["collected", "complete", "process_failed"].includes(session.status)
            && session.files_total > 0
            && session.files_completed === session.files_total
            && session.task_count > 0;
          const progressTotal = session.clips_total + session.grids_total;
          const progressDone = session.clips_completed + session.grids_completed;
          return (
            <article className="project-card" key={session.id}>
              <div className="project-title">
                <div className="project-icon"><FolderKanban size={19} /></div>
                <div><h3>{session.id}</h3><p>{formatDate(session.started_at)}</p></div>
                <span className={`project-status ${session.status}`}>{statusText[session.status]}</span>
              </div>
              <div className="project-metrics">
                <div><span>EXO 素材</span><strong>{session.files_completed}/{session.files_total}</strong><small>{formatBytes(session.bytes_downloaded)}</small></div>
                <div><span>任务</span><strong>{session.task_count}</strong><small>完整起止切点</small></div>
                <div><span>切片</span><strong>{session.clips_completed}/{session.clips_total}</strong><small>{session.camera_ids.length} 个 EXO 机位</small></div>
                <div><span>宫格</span><strong>{session.grids_completed}/{session.grids_total}</strong><small>按任务生成</small></div>
              </div>
              {processing && progressTotal > 0 && <div className="project-progress"><i style={{ width: `${Math.min(100, progressDone / progressTotal * 100)}%` }} /></div>}
              {session.errors.length > 0 && <p className="project-error">{session.errors[0]}</p>}
              <footer>
                <span><Video size={15} /> 原始素材保存在 <code>source/</code>，算法输出到 <code>clips/</code></span>
                <div className="project-actions">
                  <button className="button ghost" disabled={session.files_completed === 0} onClick={() => setMediaSession(session)}><Eye size={16} />查看素材</button>
                  <button className="button secondary" disabled={!canProcess || processing || processMutation.isPending} onClick={() => processMutation.mutate(session.id)}>
                    {processing ? <LoaderCircle className="spin" size={16} /> : <Play size={16} fill="currentColor" />}
                    {session.status === "complete" ? "重新生成" : "生成切片"}
                  </button>
                </div>
              </footer>
            </article>
          );
        })}
      </section>
      {mediaSession && <MediaPlayerDialog session={mediaSession} onClose={() => setMediaSession(null)} />}
    </div>
  );
}
