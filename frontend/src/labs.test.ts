import { describe, expect, it } from "vitest";

import { buildNetworkCommand, buildOnboardingCommand, profileLabel, recordingConfigToProfile, type CaptureProfile } from "./labs";

const profile: CaptureProfile = {
  resolution: "r4",
  fps: "p30",
  lens: "fW",
  depth: "d10",
  color: "cN",
  bitrate: "b1",
  stabilization: "e4",
};

describe("buildOnboardingCommand", () => {
  it("builds a minimal open network command", () => {
    expect(buildNetworkCommand("EGO4D", "secret123")).toBe(
      '*JOIN="EGO4D:secret123"*OPNW=1oW1!W',
    );
  });

  it("combines reconnecting open network control and capture settings", () => {
    expect(buildOnboardingCommand("EGO4D", "secret123", profile)).toBe(
      '*JOIN="EGO4D:secret123"*FAST=1*OPNW=1*BOOT=!Lwifi!SAVEwifi=!WmVr4p30fWd10cNb1e4hS0oW1!W',
    );
  });

  it("does not store quote characters in the boot script filename", () => {
    const command = buildOnboardingCommand("EGO4D", "secret123", profile);

    expect(command).toContain("*BOOT=!Lwifi!SAVEwifi=!W");
    expect(command).not.toContain('!Lwifi"');
  });

  it("rejects double quotes", () => {
    expect(() => buildOnboardingCommand('bad"ssid', "secret123", profile)).toThrow();
  });

  it("formats the selected profile", () => {
    expect(profileLabel(profile)).toBe("4K 30 FPS · Wide · 10-bit");
  });

  it("adapts the shared recording config for HERO9 onboarding", () => {
    const adapted = recordingConfigToProfile({
      resolution: "5.3K_8_7", fps: 60, lens: "hyperview", bit_depth: 10,
      color: "natural", high_bitrate: true, stabilization: "auto_boost",
      hindsight: false, shutter_speed: 120, iso: 400,
    }, true);

    expect(adapted).toMatchObject({ resolution: "r4", fps: "p60", lens: "fW", depth: "d8", color: "cG", stabilization: "e2" });
    expect(buildOnboardingCommand("EGO4D", "secret123", adapted, false, false)).not.toContain("mV");
  });
});
