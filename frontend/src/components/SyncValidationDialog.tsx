import { useRef, useState } from "react";
import { CheckCircle2, LoaderCircle, Play, X } from "lucide-react";
import { toast } from "sonner";

import { analyzeSyncValidation, getCaptureSession, updateRecordingConfig } from "../api";
import type { BatchCommandResponse, CaptureSession, RecordingConfig, SyncValidationReport } from "../types";

const preset: RecordingConfig = {
  resolution: "1080P", fps: 30, lens: "wide", bit_depth: 8, color: "natural",
  high_bitrate: false, stabilization: "off", hindsight: false, shutter_speed: 120, iso: 400,
};

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function waitForVideo(video: HTMLVideoElement): Promise<void> {
  if (video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) return Promise.resolve();
  return new Promise((resolve, reject) => {
    video.addEventListener("canplay", () => resolve(), { once: true });
    video.addEventListener("error", () => reject(new Error("同步验证视频加载失败")), { once: true });
    video.load();
  });
}

export function SyncValidationDialog({
  open, cameraCount, onClose, onApply, onStart, onStop,
}: {
  open: boolean;
  cameraCount: number;
  onClose: () => void;
  onApply: () => Promise<BatchCommandResponse>;
  onStart: () => Promise<CaptureSession>;
  onStop: (sessionId: string) => Promise<CaptureSession>;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState("ready");
  const [countdown, setCountdown] = useState<number | null>(null);
  const [report, setReport] = useState<SyncValidationReport | null>(null);

  async function run() {
    if (!stageRef.current || !videoRef.current) return;
    setReport(null);
    try {
      await stageRef.current.requestFullscreen();
      setState("正在加载逐帧二维码视频");
      await waitForVideo(videoRef.current);
      setState("正在应用预设并等待相机恢复（最长 60 秒）");
      await updateRecordingConfig(preset);
      const applied = await onApply();
      if (applied.failure_count) throw new Error(applied.results.filter((item) => !item.success).map((item) => item.message).join("；"));
      await wait(5000);
      setState("正在启动相机录制");
      const session = await onStart();
      setState("相机已经开始录制，准备播放测试片");
      for (let value = 10; value > 0; value -= 1) {
        setCountdown(value);
        await wait(1000);
      }
      setCountdown(null);
      setState("正在拍摄逐帧二维码");
      videoRef.current.currentTime = 0;
      await videoRef.current.play();
      await new Promise<void>((resolve) => videoRef.current?.addEventListener("ended", () => resolve(), { once: true }));
      setState("正在停止录制并收集素材");
      await onStop(session.id);
      if (document.fullscreenElement) await document.exitFullscreen();

      let collected = await getCaptureSession(session.id);
      while (collected.status === "collecting") {
        await wait(2000);
        collected = await getCaptureSession(session.id);
      }
      if (!(["complete", "partial"] as string[]).includes(collected.status)) {
        throw new Error(collected.errors[0] ?? "素材收集未完成");
      }
      setState("正在逐帧识别并计算偏移");
      setReport(await analyzeSyncValidation(session.id));
      setState("done");
    } catch (error) {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined);
      setState("ready");
      toast.error("同步验证失败", { description: (error as Error).message });
    }
  }

  if (!open) return null;
  const running = state !== "ready" && state !== "done";
  return (
    <div className="dialog-backdrop">
      <section className="onboarding-dialog sync-validation-dialog" role="dialog" aria-modal="true">
        <header className="dialog-header">
          <div><span>SYNC VALIDATION</span><h2>多机同步验证</h2></div>
          <button disabled={running} onClick={onClose} aria-label="关闭"><X size={21} /></button>
        </header>
        <div className="sync-validation-content">
          <div className="sync-video-stage" ref={stageRef}>
            <video ref={videoRef} src="/sync-validation-30fps.mp4" playsInline preload="auto" />
            {countdown !== null && <strong className="sync-countdown">{countdown}</strong>}
          </div>
          <div className="sync-validation-copy">
            <h3>20 秒逐帧二维码</h3>
            <p>自动应用 1080P / 30 FPS / 1/120s / ISO 400 / 防抖关闭，等待相机恢复后启动录制；保留10秒准备时间，再全屏播放、停止收集并计算相对帧差。</p>
            {report && (
              <div className="sync-report">
                <strong><CheckCircle2 size={17} /> 基准：{report.reference_camera_name}</strong>
                {report.results.map((item) => <div key={item.camera_id}><span>{item.camera_name}</span><b>{item.offset_frames === null ? "无法比较" : `${item.offset_frames > 0 ? "+" : ""}${item.offset_frames} 帧`}</b><small>{item.compared_frames} 帧有效</small></div>)}
              </div>
            )}
          </div>
        </div>
        <footer className="dialog-footer config-dialog-footer">
          <span>{running ? state : `当前选择 ${cameraCount} 台相机`}</span>
          <button className="button secondary" disabled={running || cameraCount < 2} onClick={() => void run()}>{running ? <LoaderCircle className="spin" size={17} /> : <Play size={17} fill="currentColor" />}{report ? "重新验证" : "开始一键验证"}</button>
        </footer>
      </section>
    </div>
  );
}
