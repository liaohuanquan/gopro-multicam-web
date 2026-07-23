import { describe, expect, it } from "vitest";

import { buildLiveTimecodeCommand } from "./taskTime";

describe("buildLiveTimecodeCommand", () => {
  it("使用 GoPro Labs 的 UTC 命令格式", () => {
    const date = new Date("2026-07-22T07:25:16.100Z");
    expect(buildLiveTimecodeCommand(date, "44719")).toBe("oT260722072516.100oTI44719");
  });
});
