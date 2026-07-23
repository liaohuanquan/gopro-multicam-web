import { useEffect, useMemo, useState } from "react";
import QRCode from "qrcode";
import { ArrowLeft, ArrowRight, Check, Eye, EyeOff, LoaderCircle, Radar, X } from "lucide-react";

import { buildNetworkCommand, buildOnboardingCommand, profileLabel, type CaptureProfile } from "./labs";
import type { DiscoverCameraInput } from "./types";

const defaultProfile: CaptureProfile = {
  resolution: "r4",
  fps: "p30",
  lens: "fW",
  depth: "d10",
  color: "cN",
  bitrate: "b1",
  stabilization: "e4",
};

const WIFI_SSID_KEY = "gopro-multicam.wifi-ssid";
const WIFI_PASSWORD_KEY = "gopro-multicam.wifi-password";

function QrImage({ command }: { command: string }) {
  const [source, setSource] = useState("");
  useEffect(() => {
    QRCode.toDataURL(command, { width: 420, margin: 2, errorCorrectionLevel: "M" }).then(setSource);
  }, [command]);
  return source ? <img className="onboarding-qr" src={source} alt="GoPro Labs 配置二维码" /> : null;
}

export function OnboardingDialog({
  open,
  pending,
  onClose,
  onDiscover,
}: {
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onDiscover: (input: DiscoverCameraInput) => void;
}) {
  const [step, setStep] = useState(1);
  const [showWifiPassword, setShowWifiPassword] = useState(false);
  const [ssid, setSsid] = useState(() => window.localStorage.getItem(WIFI_SSID_KEY) ?? "");
  const [wifiPassword, setWifiPassword] = useState(() => window.localStorage.getItem(WIFI_PASSWORD_KEY) ?? "");
  const [profile, setProfile] = useState<CaptureProfile>(defaultProfile);
  const [qrMode, setQrMode] = useState<"setup" | "network" | "control" | "address" | "cohn" | "credentials" | "reset">("setup");

  useEffect(() => {
    window.localStorage.setItem(WIFI_SSID_KEY, ssid);
  }, [ssid]);

  useEffect(() => {
    window.localStorage.setItem(WIFI_PASSWORD_KEY, wifiPassword);
  }, [wifiPassword]);

  const onboardingCommand = useMemo(() => {
    try { return buildOnboardingCommand(ssid, wifiPassword, profile); } catch { return ""; }
  }, [ssid, wifiPassword, profile]);
  const networkCommand = useMemo(() => {
    try { return buildNetworkCommand(ssid, wifiPassword); } catch { return ""; }
  }, [ssid, wifiPassword]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="onboarding-dialog" role="dialog" aria-modal="true" aria-label="添加 GoPro">
        <header className="dialog-header">
          <div><span>ADD CAMERA</span><h2>扫码添加 HERO13</h2></div>
          <button onClick={onClose} aria-label="关闭"><X size={21} /></button>
        </header>
        <div className="stepper">
          {["配置参数", "扫码并发现"].map((label, index) => (
            <div className={step >= index + 1 ? "active" : ""} key={label}><b>{index + 1}</b><span>{label}</span></div>
          ))}
        </div>

        {step === 1 && (
          <div className="dialog-body form-step">
            <div className="form-section">
              <h3>采集网络</h3>
              <label>Wi-Fi 名称<input value={ssid} onChange={(event) => setSsid(event.target.value)} placeholder="例如 EGO4D-CAPTURE" /></label>
              <label>Wi-Fi 密码<div className="password-input"><input type={showWifiPassword ? "text" : "password"} value={wifiPassword} onChange={(event) => setWifiPassword(event.target.value)} /><button onClick={() => setShowWifiPassword((value) => !value)}>{showWifiPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
              <p>Wi-Fi 名称和密码只保存在当前浏览器中，打开添加设备时会自动填写；不会发送到服务器。相机控制本身不需要用户名和密码。</p>
            </div>
            <div className="form-section">
              <h3>录制参数</h3>
              <div className="profile-grid">
                <label>分辨率<select value={profile.resolution} onChange={(event) => setProfile({ ...profile, resolution: event.target.value as CaptureProfile["resolution"] })}><option value="r4">4K 16:9</option><option value="r5X">5.3K 8:7</option><option value="r1">1080P</option></select></label>
                <label>帧率<select value={profile.fps} onChange={(event) => setProfile({ ...profile, fps: event.target.value as CaptureProfile["fps"] })}><option value="p30">30 FPS</option><option value="p25">25 FPS</option><option value="p24">24 FPS</option><option value="p50">50 FPS</option><option value="p60">60 FPS</option></select></label>
                <label>镜头<select value={profile.lens} onChange={(event) => setProfile({ ...profile, lens: event.target.value as CaptureProfile["lens"] })}><option value="fW">Wide</option><option value="fL">Linear</option><option value="fV">HyperView</option></select></label>
                <label>色深<select value={profile.depth} onChange={(event) => setProfile({ ...profile, depth: event.target.value as CaptureProfile["depth"] })}><option value="d10">10-bit</option><option value="d8">8-bit</option></select></label>
                <label>色彩<select value={profile.color} onChange={(event) => setProfile({ ...profile, color: event.target.value as CaptureProfile["color"] })}><option value="cN">Natural</option><option value="cF">Flat</option><option value="cG">Vibrant</option></select></label>
                <label>防抖<select value={profile.stabilization} onChange={(event) => setProfile({ ...profile, stabilization: event.target.value as CaptureProfile["stabilization"] })}><option value="e4">AutoBoost</option><option value="e2">High</option><option value="e0">关闭</option></select></label>
              </div>
              <label className="toggle-row"><input type="checkbox" checked={profile.bitrate === "b1"} onChange={(event) => setProfile({ ...profile, bitrate: event.target.checked ? "b1" : "b0" })} />高码率</label>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="dialog-body qr-step">
            <div className="qr-copy">
              <span>GO PRO LABS</span><h3>让相机扫描这个二维码</h3>
              <div className="qr-tabs onboarding-qr-tabs"><button className={qrMode === "setup" ? "active" : ""} onClick={() => setQrMode("setup")}>入网配置</button><button className={qrMode === "network" ? "active" : ""} onClick={() => setQrMode("network")}>仅配网测试</button><button className={qrMode === "control" ? "active" : ""} onClick={() => setQrMode("control")}>修复网页控制</button><button className={qrMode === "address" ? "active" : ""} onClick={() => setQrMode("address")}>显示相机 IP</button><button className={qrMode === "cohn" ? "active" : ""} onClick={() => setQrMode("cohn")}>1 初始化控制凭据</button><button className={qrMode === "credentials" ? "active" : ""} onClick={() => setQrMode("credentials")}>2 写入控制凭据</button><button className={qrMode === "reset" ? "active danger" : "danger"} onClick={() => setQrMode("reset")}>重置 Labs</button></div>
              {qrMode === "setup"
                ? <ol><li>确认 HERO13 已安装 Labs 固件</li><li>停留在视频预览画面并对准二维码</li><li>等待相机连接 Wi-Fi，再点击下方扫描按钮</li></ol>
                : qrMode === "network"
                  ? <ol><li>确认上一步填写的是目标 Wi-Fi 名称和密码</li><li>扫描后立刻移开相机，等待 joined network</li><li>此二维码不写启动脚本和录制参数</li></ol>
                : qrMode === "control"
                  ? <ol><li>扫描官方最小永久命令，启用免密码 HTTP 控制</li><li>确认识别后彻底关机，拔电池等待 10 秒再开机</li><li>相机重新加入网络后，再点击下方扫描按钮</li></ol>
                  : qrMode === "address"
                    ? <ol><li>让已经入网的相机扫描右侧二维码</li><li>相机屏幕会显示当前局域网 IP 5 秒</li><li>每台相机的 IP 应该不同</li></ol>
                    : qrMode === "cohn"
                      ? <ol><li>每台相机先扫描一次此二维码</li><li>等待相机完成 COHN 控制凭据初始化</li><li>随后选择“2 写入控制凭据”继续扫描</li></ol>
                      : qrMode === "credentials"
                        ? <ol><li>初始化完成后扫描右侧二维码</li><li>完整控制凭据会写入 SD 卡 MISC/qrlog.txt</li><li>每台相机分别执行并保存自己的文件</li></ol>
                        : <ol><li>仅用于控制服务异常的相机</li><li>扫描后在相机屏幕确认重置，等待自动重启</li><li>不会删除视频；重启后重新扫描一次入网配置</li></ol>}
              <div className="profile-summary"><Check size={17} />{profileLabel(profile)}<br />自动重连 · 无控制密码 · Hindsight 关闭</div>
              <p className="network-warning">开放控制只适合隔离的室内采集 Wi-Fi，请勿连接公共或办公网络。</p>
            </div>
            <div className="qr-frame"><QrImage command={qrMode === "setup" ? onboardingCommand : qrMode === "network" ? networkCommand : qrMode === "control" ? "*OPNW=1" : qrMode === "address" ? "$ADDR=5" : qrMode === "cohn" ? "$COHN=1" : qrMode === "credentials" ? "$SHPS=1" : "!RESET!1OR"} /><small>{qrMode === "setup" || qrMode === "network" ? "二维码含 Wi-Fi 密码，请勿截图外传" : qrMode === "control" ? "永久启用 HTTP 控制；扫码后需要冷启动" : qrMode === "address" ? "扫描后在相机屏幕查看 IP" : qrMode === "cohn" ? "为此相机初始化 COHN 控制凭据" : qrMode === "credentials" ? "完整凭据写入 SD 卡 MISC/qrlog.txt" : "清除 Labs 永久配置并重启，不删除视频"}</small></div>
          </div>
        )}

        <footer className="dialog-footer">
          <button className="button ghost" disabled={step === 1 || pending} onClick={() => setStep(1)}><ArrowLeft size={17} />上一步</button>
          {step === 1
            ? <button className="button secondary" disabled={!onboardingCommand || pending} onClick={() => setStep(2)}>下一步<ArrowRight size={17} /></button>
            : <button className="button secondary" disabled={pending} onClick={() => onDiscover({ profile_label: profileLabel(profile) })}>{pending ? <LoaderCircle className="spin" size={17} /> : <Radar size={17} />}扫描局域网并加入设备组</button>}
        </footer>
      </section>
    </div>
  );
}
