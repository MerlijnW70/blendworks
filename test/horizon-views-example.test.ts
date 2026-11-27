import { execFileSync } from "node:child_process";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Shot = {
  land: { triangles: number; border: { within: boolean }; rings: { count: number }; curvature: { radius: number } };
  forest: { counts: { cards: number; near: number }; cover: { covered: number } };
  haze: { method: string };
};
type Summary = { shots: Record<string, Shot>; commands: { cmd: string }[] };

describe("the horizon views example", workBudget(600_000), () => {
  it("builds a view from a hill over distant land with forest and haze, and renders it", () => {
    const out = freshDir("horizon-views-example");
    const env = {
      ...process.env,
      BLENDWORKS_SHOT_WIDTH: "64",
      BLENDWORKS_SHOT_HEIGHT: "36",
      BLENDWORKS_SHOT_SAMPLES: "2",
      BLENDWORKS_SHOT_SECONDS: "60",
      BLENDWORKS_HORIZON_TREES: "0.05",
      BLENDWORKS_HORIZON_DETAIL: "24",
      BLENDWORKS_HORIZON_FRAMES: "4",
      BLENDWORKS_HORIZON_PIXELS: "32",
      BLENDWORKS_DEVICE: "cpu",
    };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/horizon_views.py", "--", out, "hill"], { env, stdio: "pipe" });
    const summary = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary;
    const used = new Set(summary.commands.map((entry) => entry.cmd));
    for (const command of ["distant_land", "distant_forest", "atmosphere", "render_final"]) expect(used.has(command), command).toBe(true);
    const hill = summary.shots["hill"]!;
    expect(hill.land.border.within).toBe(true);
    expect(hill.land.rings.count).toBeGreaterThan(3);
    expect(hill.land.curvature.radius).toBe(6371000);
    expect(hill.forest.cover.covered).toBeGreaterThan(0.3);
    expect(hill.haze.method).toBe("depth");
    expect(statSync(join(out, "hill.png")).size).toBeGreaterThan(500);
  });
});
