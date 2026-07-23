import { Plus, ShieldCheck } from "lucide-react";

export function WorkspaceHeader({ onAddCamera }: { onAddCamera: () => void }) {
  return (
    <header className="workspace-header">
      <div><h2>采集控制</h2></div>
      <div className="topbar-actions">
        <div className="real-badge"><ShieldCheck size={15} /> 局域网设备</div>
        <button className="button secondary add-camera-button" onClick={onAddCamera}><Plus size={17} />扫码添加设备</button>
      </div>
    </header>
  );
}
