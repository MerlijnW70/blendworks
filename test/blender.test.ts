import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { BLENDER_VERSION, blenderPath } from "../src/blender.js";
import { useBlenderSlot } from "./setup/slot.js";

useBlenderSlot();

describe("the pinned Blender", () => {
  it("runs headless at the pinned version", () => {
    const out = execFileSync(blenderPath(), ["--background", "--factory-startup", "--version"], { encoding: "utf8" });
    expect(out).toContain(`Blender ${BLENDER_VERSION}`);
  });
});
