import { ExternalLink, FolderKanban, LayoutDashboard } from "lucide-react";

import { LiveTimecodeCommand } from "./LiveTimecodeCommand";

export interface CaptureSummary {
  online: number;
  ready: number;
  recording: number;
}

export interface AppSidebarProps {
  summary: CaptureSummary;
  total: number;
  timecodeUrl: string;
  currentPage: "capture" | "projects";
  onNavigate: (page: "capture" | "projects") => void;
}

export function AppSidebar({ summary, total, timecodeUrl, currentPage, onNavigate }: AppSidebarProps) {
  return (
    <aside className="app-sidebar">
      <div className="sidebar-chrome">
        <div className="brand">
          <div><h1>采集控制台</h1><p>GoPro HERO9 / HERO13</p></div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="主导航">
        <button className={currentPage === "capture" ? "active" : ""} onClick={() => onNavigate("capture")}><LayoutDashboard size={16} />开始采集</button>
        <button className={currentPage === "projects" ? "active" : ""} onClick={() => onNavigate("projects")}><FolderKanban size={16} />管理项目</button>
      </nav>

      {currentPage === "capture" && <section className="sidebar-section" aria-label="采集状态">
        <div className="panel-heading"><span>设备管理</span><small>实时</small></div>
        <div className="sidebar-status-list">
          <div><span className={summary.online === total && total > 0 ? "healthy" : ""}>设备在线</span><strong>{summary.online}/{total}</strong></div>
          <div><span className={summary.ready === total && total > 0 ? "healthy" : ""}>拍摄就绪</span><strong>{summary.ready}/{total}</strong></div>
          <div><span className={summary.recording ? "recording" : ""}>正在录制</span><strong>{summary.recording}/{total}</strong></div>
        </div>
      </section>}

      {currentPage === "capture" && <section className="sidebar-section timecode-sidebar">
        <div className="sidebar-section-title"><span>UTC</span><div><h2>管理时间码</h2><p>开拍前依次扫描</p></div></div>
        <LiveTimecodeCommand />
        <a className="button secondary" href={timecodeUrl} target="_blank" rel="noreferrer">动态二维码 <ExternalLink size={15} /></a>
      </section>}
    </aside>
  );
}
