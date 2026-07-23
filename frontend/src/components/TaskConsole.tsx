import { useEffect, useState } from "react";
import { Clock3, Download, Square } from "lucide-react";

import { findActiveTask, formatUtc } from "../taskTime";
import type { TaskEvent, TaskEventListResponse } from "../types";

export interface TaskConsoleProps {
  data: TaskEventListResponse | undefined;
  taskName: string;
  onTaskNameChange: (value: string) => void;
  onCreateEvent: (event: "start" | "end", active: TaskEvent | null) => void;
  pending: boolean;
}

export function TaskConsole({ data, taskName, onTaskNameChange, onCreateEvent, pending }: TaskConsoleProps) {
  const [now, setNow] = useState(Date.now());
  const [serverOffset, setServerOffset] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (data) setServerOffset(Date.parse(data.server_utc) - Date.now());
  }, [data]);

  const events = data?.events ?? [];
  const active = findActiveTask(events);
  const latest = events.at(-1);
  const remainingMs = latest ? Math.max(0, Date.parse(latest.utc_at) - (now + serverOffset)) : 0;
  const countdown = remainingMs > 0 ? (remainingMs / 1000).toFixed(1) : null;

  function exportEvents() {
    const payload = data ?? { server_utc: new Date().toISOString(), events: [] };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `gopro-task-events-${new Date().toISOString().replaceAll(":", "-")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className={`task-console ${active ? "task-active" : ""}`} aria-label="UTC 任务切片">
      <div className="task-primary">
        <div className="task-heading">
          <h2>任务</h2>
          <span>{active ? `进行中 · ${formatUtc(active.utc_at)} UTC` : "未开始"}</span>
        </div>
        <div className="task-form">
          <input value={active?.task_name ?? taskName} disabled={Boolean(active)} maxLength={64} onChange={(event) => onTaskNameChange(event.target.value)} aria-label="任务名称" />
          {!active ? (
            <button className="button task-start" disabled={pending || Boolean(countdown) || !taskName.trim()} onClick={() => onCreateEvent("start", null)}><span className="rec-dot" /> 开始任务</button>
          ) : (
            <button className="button task-end" disabled={pending || Boolean(countdown)} onClick={() => onCreateEvent("end", active)}><Square size={15} fill="currentColor" /> 结束任务</button>
          )}
        </div>
        <div className="task-rule">操作延迟 3 秒记录</div>
      </div>

      <div className="task-timeline">
        <div className="task-timeline-header">
          <div><span>UTC</span><strong>{data ? formatUtc(data.server_utc) : "--:--:--.---"}</strong></div>
          <button onClick={exportEvents} disabled={!events.length}><Download size={15} /> 导出</button>
        </div>
        {countdown && latest ? (
          <div className="countdown-card" role="status" aria-live="polite"><small>{latest.event === "start" ? "任务开始" : "任务结束"}</small><strong>{countdown}</strong><span>秒</span></div>
        ) : events.length ? (
          <div className="event-list">
            {events.slice(-5).reverse().map((event) => (
              <div key={event.id}><span className={event.event}>{event.event === "start" ? "开始" : "结束"}</span><strong>{event.task_name}</strong><time>{formatUtc(event.utc_at)}</time></div>
            ))}
          </div>
        ) : (
          <div className="event-empty"><Clock3 size={18} /><span>暂无记录</span></div>
        )}
      </div>
    </section>
  );
}
