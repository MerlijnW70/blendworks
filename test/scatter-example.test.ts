import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; count: number | null; min_pair_distance: number | null; masked_out: number | null; fitted_exponent: number | null };

const MIN_DISTANCE = 2.0 * 0.3;

describe("the scatter rocks example", workBudget(240_000), () => {
  it("scatters a power-law rock set over a heightfield tile with commands only and renders it", () => {
    const out = freshDir("scatter-rocks-example");
    const env = { ...process.env, BLENDWORKS_TERRAIN_RESOLUTION: "81", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/scatter_rocks.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    expect(log.filter((entry) => entry.cmd === "heightfield")).toHaveLength(1);
    const scatter = log.filter((entry) => entry.cmd === "scatter");
    expect(scatter).toHaveLength(1);
    expect(scatter[0]?.count).toBeGreaterThan(300);
    expect(scatter[0]?.min_pair_distance).toBeGreaterThanOrEqual(MIN_DISTANCE - 1e-6);
    expect(scatter[0]?.masked_out).toBeGreaterThan(0.3);
    expect(Math.abs((scatter[0]?.fitted_exponent ?? 0) + 2)).toBeLessThan(0.3);
    for (const name of ["overview", "slope", "closeup", "top"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "scatter-rocks.blend"))).toBe(true);
  });
});
