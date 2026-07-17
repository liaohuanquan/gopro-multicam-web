import { describe, expect, it } from "vitest";

import { formatDuration, formatSyncAge } from "./format";

describe("formatDuration", () => {
  it("formats recording duration", () => {
    expect(formatDuration(3661)).toBe("01:01:01");
  });
});

describe("formatSyncAge", () => {
  it("shows unsynced state", () => {
    expect(formatSyncAge(null)).toBe("未同步");
  });
});

