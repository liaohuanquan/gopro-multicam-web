import { describe, expect, it } from "vitest";

import { toggleSelectedCamera } from "./useCaptureConsole";

describe("toggleSelectedCamera", () => {
  it("首次取消时从默认全选中移除目标相机", () => {
    expect(toggleSelectedCamera(null, ["GP02", "GP03"], "GP02")).toEqual(["GP03"]);
  });

  it("允许明确取消所有相机，不会重新回到默认全选", () => {
    expect(toggleSelectedCamera(["GP03"], ["GP02", "GP03"], "GP03")).toEqual([]);
  });
});
