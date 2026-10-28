import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; name: string | null; manifold: boolean | null; volume: number | null; wall_min: number | null };

describe("the shells example", workBudget(240_000), () => {
  it("builds three shells with commands only, with materials, and renders them", () => {
    const out = freshDir("shells-example");
    const env = { ...process.env, BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/shells.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const shells = log.filter((entry) => entry.cmd === "shell");
    expect(shells.map((entry) => entry.name)).toEqual(["conch", "ammonite", "ribbed_fan"]);
    for (const entry of shells) {
      expect(entry.manifold, `${entry.name} manifold`).toBe(true);
      expect(entry.volume, `${entry.name} volume`).toBeGreaterThan(0);
    }
    expect(shells[0]?.wall_min).toBeGreaterThanOrEqual(0.002);
    expect(shells[1]?.wall_min).toBeGreaterThanOrEqual(0.003);
    expect(log.filter((entry) => entry.cmd === "assign_material")).toHaveLength(4);
    for (const name of ["overview", "conch", "ammonite", "ribbed_fan"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "shells.blend"))).toBe(true);
  });
});
