import { useEffect, useState } from "react";
import { LoaderCircle, Save, SlidersHorizontal, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { deleteRecordingPreset, getRecordingConfig, getRecordingPresets, saveRecordingPreset, updateRecordingConfig } from "../api";
import type { RecordingConfig, RecordingPreset } from "../types";

const emptyConfig: RecordingConfig = {
  resolution: "4K",
  fps: 30,
  lens: "wide",
  bit_depth: 10,
  color: "natural",
  high_bitrate: true,
  stabilization: "auto_boost",
  hindsight: false,
  shutter_speed: null,
  iso: null,
};

export function RecordingConfigDialog({
  open,
  selectedCount,
  onClose,
  onApply,
}: {
  open: boolean;
  selectedCount: number;
  onClose: () => void;
  onApply: () => void;
}) {
  const [config, setConfig] = useState<RecordingConfig>(emptyConfig);
  const [presets, setPresets] = useState<RecordingPreset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presetName, setPresetName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    Promise.all([getRecordingConfig(), getRecordingPresets()])
      .then(([recordingConfig, recordingPresets]) => {
        setConfig(recordingConfig);
        setPresets(recordingPresets);
        setSelectedPreset("");
        setPresetName("");
      })
      .catch((error: Error) => toast.error("读取录制参数失败", { description: error.message }))
      .finally(() => setLoading(false));
  }, [open]);

  function selectPreset(name: string) {
    setSelectedPreset(name);
    const preset = presets.find((item) => item.name === name);
    if (preset) setConfig(preset.config);
  }

  async function savePreset() {
    const name = presetName.trim();
    if (!name) {
      toast.error("请先填写预设名称");
      return;
    }
    setSaving(true);
    try {
      const saved = await saveRecordingPreset(name, config);
      setPresets((current) => [...current.filter((item) => item.name !== saved.name), saved]);
      setSelectedPreset(saved.name);
      setPresetName("");
      toast.success(`预设“${saved.name}”已保存`);
    } catch (error) {
      toast.error("保存预设失败", { description: (error as Error).message });
    } finally {
      setSaving(false);
    }
  }

  async function removePreset() {
    const preset = presets.find((item) => item.name === selectedPreset);
    if (!preset || preset.builtin) return;
    setSaving(true);
    try {
      await deleteRecordingPreset(preset.name);
      setPresets((current) => current.filter((item) => item.name !== preset.name));
      setSelectedPreset("");
      toast.success(`预设“${preset.name}”已删除`);
    } catch (error) {
      toast.error("删除预设失败", { description: (error as Error).message });
    } finally {
      setSaving(false);
    }
  }

  async function save(apply: boolean) {
    setSaving(true);
    try {
      await updateRecordingConfig(config);
      toast.success("录制参数已保存到配置文件");
      if (apply) onApply();
      onClose();
    } catch (error) {
      toast.error("保存录制参数失败", { description: (error as Error).message });
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="onboarding-dialog recording-config-dialog" role="dialog" aria-modal="true" aria-label="录制参数">
        <header className="dialog-header">
          <div><span>RECORDING CONFIG</span><h2>统一录制参数</h2></div>
          <button disabled={saving} onClick={onClose} aria-label="关闭"><X size={21} /></button>
        </header>
        <div className="dialog-body recording-config-body">
          {loading ? <div className="config-loading"><LoaderCircle className="spin" />正在读取配置…</div> : (
            <div className="form-section">
              <div className="config-presets">
                <label>录制预设<select value={selectedPreset} onChange={(event) => selectPreset(event.target.value)}><option value="">当前参数</option>{presets.map((preset) => <option key={preset.name} value={preset.name}>{preset.name}{preset.builtin ? "（内置）" : ""}</option>)}</select></label>
                <div className="config-preset-create"><input value={presetName} maxLength={32} placeholder="自定义预设名称" onChange={(event) => setPresetName(event.target.value)} /><button type="button" disabled={saving} onClick={() => void savePreset()}><Save size={15} />保存为预设</button><button className="danger" type="button" disabled={saving || !selectedPreset || presets.find((item) => item.name === selectedPreset)?.builtin} onClick={() => void removePreset()} title="删除当前自定义预设"><Trash2 size={15} /></button></div>
              </div>
              <div className="profile-grid">
                <label>分辨率<select value={config.resolution ?? ""} onChange={(event) => setConfig({ ...config, resolution: event.target.value as RecordingConfig["resolution"] })}><option value="">不修改</option><option value="1080P">1080P</option><option value="4K">4K 16:9</option><option value="5.3K_8_7">5.3K 8:7</option></select></label>
                <label>帧率<select value={config.fps ?? ""} onChange={(event) => setConfig({ ...config, fps: event.target.value ? Number(event.target.value) as RecordingConfig["fps"] : null })}><option value="">不修改</option>{[24, 25, 30, 50, 60].map((fps) => <option key={fps} value={fps}>{fps} FPS</option>)}</select></label>
                <label>镜头<select value={config.lens ?? ""} onChange={(event) => setConfig({ ...config, lens: event.target.value as RecordingConfig["lens"] })}><option value="">不修改</option><option value="wide">Wide</option><option value="linear">Linear</option><option value="hyperview">HyperView</option></select></label>
                <label>色深<select value={config.bit_depth ?? ""} onChange={(event) => setConfig({ ...config, bit_depth: event.target.value ? Number(event.target.value) as RecordingConfig["bit_depth"] : null })}><option value="">不修改</option><option value="8">8-bit</option><option value="10">10-bit</option></select></label>
                <label>色彩<select value={config.color ?? ""} onChange={(event) => setConfig({ ...config, color: event.target.value as RecordingConfig["color"] })}><option value="">不修改</option><option value="natural">Natural</option><option value="flat">Flat</option><option value="vibrant">Vibrant</option></select></label>
                <label>防抖<select value={config.stabilization ?? ""} onChange={(event) => setConfig({ ...config, stabilization: event.target.value as RecordingConfig["stabilization"] })}><option value="">不修改</option><option value="auto_boost">AutoBoost</option><option value="high">High</option><option value="off">关闭</option></select></label>
                <label>码率<select value={config.high_bitrate === null ? "" : String(config.high_bitrate)} onChange={(event) => setConfig({ ...config, high_bitrate: event.target.value === "" ? null : event.target.value === "true" })}><option value="">不修改</option><option value="true">高码率</option><option value="false">标准码率</option></select></label>
                <label>Hindsight<select value={config.hindsight === null ? "" : String(config.hindsight)} onChange={(event) => setConfig({ ...config, hindsight: event.target.value === "" ? null : event.target.value === "true" })}><option value="">不修改</option><option value="false">关闭</option><option value="true">开启</option></select></label>
                <label>快门<select value={config.shutter_speed ?? ""} onChange={(event) => setConfig({ ...config, shutter_speed: event.target.value ? Number(event.target.value) as RecordingConfig["shutter_speed"] : null })}><option value="">不修改</option><option value="0">自动</option><option value="120">1/120s</option><option value="240">1/240s</option><option value="480">1/480s</option></select></label>
                <label>ISO（固定）<select value={config.iso ?? ""} onChange={(event) => setConfig({ ...config, iso: event.target.value ? Number(event.target.value) as RecordingConfig["iso"] : null })}><option value="">不修改</option>{[100, 200, 400, 800, 1600].map((iso) => <option key={iso} value={iso}>ISO {iso}</option>)}</select></label>
              </div>
              <p>选择“不修改”时不会向相机下发该项。HERO9 会自动转换为 8-bit、29.97/59.94、Wide/Linear 和 HyperSmooth High；其不支持的 Wi-Fi Labs 项不会下发。当前参数和自定义预设都保存在 config.json。</p>
            </div>
          )}
        </div>
        <footer className="dialog-footer config-dialog-footer">
          <span>当前选择 {selectedCount} 台相机</span>
          <div>
            <button className="button ghost" disabled={loading || saving} onClick={() => void save(false)}>仅保存</button>
            <button className="button secondary" disabled={loading || saving || selectedCount === 0} onClick={() => void save(true)}>{saving ? <LoaderCircle className="spin" size={17} /> : <SlidersHorizontal size={17} />}保存并应用</button>
          </div>
        </footer>
      </section>
    </div>
  );
}
