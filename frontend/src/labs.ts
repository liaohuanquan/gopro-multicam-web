import type { RecordingConfig } from "./types";

export interface CaptureProfile {
  resolution: "r1" | "r4" | "r5X";
  fps: "p24" | "p25" | "p30" | "p50" | "p60";
  lens: "fW" | "fL" | "fV";
  depth: "d8" | "d10";
  color: "cN" | "cF" | "cG";
  bitrate: "b0" | "b1";
  stabilization: "e0" | "e2" | "e4";
}

export function recordingConfigToProfile(config: RecordingConfig, hero9 = false): CaptureProfile {
  const profile: CaptureProfile = {
    resolution: config.resolution === "1080P" ? "r1" : config.resolution === "5.3K_8_7" ? "r5X" : "r4",
    fps: config.fps === 24 ? "p24" : config.fps === 25 ? "p25" : config.fps === 50 ? "p50" : config.fps === 60 ? "p60" : "p30",
    lens: config.lens === "linear" ? "fL" : config.lens === "hyperview" ? "fV" : "fW",
    depth: config.bit_depth === 8 ? "d8" : "d10",
    color: config.color === "flat" ? "cF" : config.color === "vibrant" ? "cG" : "cN",
    bitrate: config.high_bitrate === false ? "b0" : "b1",
    stabilization: config.stabilization === "off" ? "e0" : config.stabilization === "high" ? "e2" : "e4",
  };
  if (!hero9) return profile;
  return {
    ...profile,
    resolution: profile.resolution === "r5X" ? "r4" : profile.resolution,
    lens: profile.lens === "fV" ? "fW" : profile.lens,
    depth: "d8",
    color: profile.color === "cN" ? "cG" : profile.color,
    stabilization: profile.stabilization === "e4" ? "e2" : profile.stabilization,
  };
}

function validateWifiCredentials(ssid: string, password: string): void {
  if (!ssid.trim() || !password) throw new Error("Wi-Fi 名称和密码不能为空");
  if (ssid.includes('"') || password.includes('"')) throw new Error('Wi-Fi 名称和密码暂不支持英文双引号');
}

export function buildNetworkCommand(ssid: string, password: string, openNetwork = true): string {
  validateWifiCredentials(ssid, password);
  return `*JOIN="${ssid}:${password}"${openNetwork ? "*OPNW=1" : ""}oW1!W`;
}

export function buildOnboardingCommand(
  ssid: string,
  password: string,
  profile: CaptureProfile,
  openNetwork = true,
  includeRecordingProfile = true,
): string {
  validateWifiCredentials(ssid, password);
  return [
    `*JOIN="${ssid}:${password}"`,
    "*FAST=1",
    openNetwork ? "*OPNW=1" : "",
    "*BOOT=!Lwifi",
    "!SAVEwifi=!W",
    includeRecordingProfile ? "mV" : "",
    includeRecordingProfile ? profile.resolution : "",
    includeRecordingProfile ? profile.fps : "",
    includeRecordingProfile ? profile.lens : "",
    includeRecordingProfile ? profile.depth : "",
    includeRecordingProfile ? profile.color : "",
    includeRecordingProfile ? profile.bitrate : "",
    includeRecordingProfile ? profile.stabilization : "",
    includeRecordingProfile ? "hS0" : "",
    "oW1",
    "!W",
  ].join("");
}

export function profileLabel(profile: CaptureProfile, broadcastRates = false): string {
  const labels = {
    resolution: { r1: "1080P", r4: "4K", r5X: "5.3K 8:7" },
    fps: { p24: "24 FPS", p25: "25 FPS", p30: "30 FPS", p50: "50 FPS", p60: "60 FPS" },
    lens: { fW: "Wide", fL: "Linear", fV: "HyperView" },
    depth: { d8: "8-bit", d10: "10-bit" },
  } as const;
  const fpsLabel = broadcastRates
    ? { p24: "23.976 FPS", p25: "25 FPS", p30: "29.97 FPS", p50: "50 FPS", p60: "59.94 FPS" }[profile.fps]
    : labels.fps[profile.fps];
  return `${labels.resolution[profile.resolution]} ${fpsLabel} · ${labels.lens[profile.lens]} · ${labels.depth[profile.depth]}`;
}
