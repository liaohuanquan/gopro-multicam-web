import { describe, expect, it } from "vitest";

import { buildNetworkCommand, buildOnboardingCommand, profileLabel, type CaptureProfile } from "./labs";

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
      '*JOIN="EGO4D:secret123"*FAST=1*OPNW=1*BOOT="!Lwifi"!SAVEwifi="!W"mVr4p30fWd10cNb1e4hS0oW1!W',
    );
  });

  it("rejects double quotes", () => {
    expect(() => buildOnboardingCommand('bad"ssid', "secret123", profile)).toThrow();
  });

  it("formats the selected profile", () => {
    expect(profileLabel(profile)).toBe("4K 30 FPS · Wide · 10-bit");
  });
});
