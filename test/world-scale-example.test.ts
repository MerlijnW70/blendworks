import { execFileSync } from "node:child_process";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Summary = {
  camera: { location: number[]; distance_from_origin: number };
  land: { tiles: number; reach: number };
  haze: { visibility: number; bounds: number[][] };
  validated_calls: number;
  commands: { cmd: string }[];
};

describe("the world scale example", workBudget(400_000), () => {
  it("validates its plan, then builds land to 108 km around a camera 15 km out and renders it with haze", () => {
    const out = freshDir("world-scale-example");
    const env = {
      ...process.env,
      BLENDWORKS_WORLD_DETAIL: "0.03",
      BLENDWORKS_SHOT_WIDTH: "64",
      BLENDWORKS_SHOT_HEIGHT: "36",
      BLENDWORKS_SHOT_SAMPLES: "2",
      BLENDWORKS_SHOT_SECONDS: "60",
      BLENDWORKS_DEVICE: "cpu",
    };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/world_scale.py", "--", out], { env, stdio: "pipe" });
    const summary = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary;
    expect(summary.camera.distance_from_origin).toBeCloseTo(15_000, 0);
    expect(summary.land.reach).toBeGreaterThanOrEqual(100_000);
    expect(summary.haze.visibility).toBeGreaterThan(10_000);
    const [low, high] = summary.haze.bounds as [number[], number[]];
    expect(Math.min(-low[0]!, -low[1]!, high[0]!, high[1]!)).toBeGreaterThanOrEqual(100_000);
    const used = summary.commands.map((entry) => entry.cmd);
    expect(used[0]).toBe("validate");
    expect(used).toContain("render_final");
    expect(summary.commands.length).toBe(summary.validated_calls + 5);
    expect(statSync(join(out, "world-scale.png")).size).toBeGreaterThan(500);
  });
});
