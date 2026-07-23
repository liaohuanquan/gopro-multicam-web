export interface CaptureProfile {
  resolution: "r1" | "r4" | "r5X";
  fps: "p24" | "p25" | "p30" | "p50" | "p60";
  lens: "fW" | "fL" | "fV";
  depth: "d8" | "d10";
  color: "cN" | "cF" | "cG";
  bitrate: "b0" | "b1";
  stabilization: "e0" | "e2" | "e4";
}

function validateWifiCredentials(ssid: string, password: string): void {
  if (!ssid.trim() || !password) throw new Error("Wi-Fi 名称和密码不能为空");
  if (ssid.includes('"') || password.includes('"')) throw new Error('Wi-Fi 名称和密码暂不支持英文双引号');
}

export function buildNetworkCommand(ssid: string, password: string): string {
  validateWifiCredentials(ssid, password);
  return `*JOIN="${ssid}:${password}"*OPNW=1oW1!W`;
}

export function buildOnboardingCommand(
  ssid: string,
  password: string,
  profile: CaptureProfile,
): string {
  validateWifiCredentials(ssid, password);
  return [
    `*JOIN="${ssid}:${password}"`,
    "*FAST=1",
    "*OPNW=1",
    '*BOOT="!Lwifi"',
    '!SAVEwifi="!W"',
    "mV",
    profile.resolution,
    profile.fps,
    profile.lens,
    profile.depth,
    profile.color,
    profile.bitrate,
    profile.stabilization,
    "hS0",
    "oW1",
    "!W",
  ].join("");
}

export function profileLabel(profile: CaptureProfile): string {
  const labels = {
    resolution: { r1: "1080P", r4: "4K", r5X: "5.3K 8:7" },
    fps: { p24: "24 FPS", p25: "25 FPS", p30: "30 FPS", p50: "50 FPS", p60: "60 FPS" },
    lens: { fW: "Wide", fL: "Linear", fV: "HyperView" },
    depth: { d8: "8-bit", d10: "10-bit" },
  } as const;
  return `${labels.resolution[profile.resolution]} ${labels.fps[profile.fps]} · ${labels.lens[profile.lens]} · ${labels.depth[profile.depth]}`;
}
