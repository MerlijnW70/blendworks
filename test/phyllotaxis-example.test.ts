import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; count: number | null; phyllotaxis: { divergence: number; area_per_organ: number } | null };

describe("the phyllotaxis example", workBudget(240_000), () => {
  it("builds a sunflower head, a pine cone and a succulent rosette with commands only and renders them", () => {
    const out = freshDir("phyllotaxis-example");
    const env = { ...process.env, BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/phyllotaxis.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const placed = Object.fromEntries(log.filter((entry) => entry.cmd === "instances").map((entry, index) => [index, entry]));
    expect(Object.keys(placed)).toHaveLength(5);
    expect(placed[0]?.count).toBe(1100);
    expect(placed[0]?.phyllotaxis?.divergence).toBeCloseTo(137.50776405, 7);
    expect(placed[1]?.count).toBe(34);
    expect(placed[2]?.count).toBe(55);
    expect(placed[3]?.count).toBe(89);
    expect(placed[4]?.count).toBe(89);
    expect(log.filter((entry) => entry.cmd === "material_procedural").length).toBeGreaterThanOrEqual(6);
    for (const name of ["sunflower", "sunflower-seeds", "pine-cone", "pine-cone-top", "rosette", "rosette-top", "overview"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "phyllotaxis.blend"))).toBe(true);
  });
});
