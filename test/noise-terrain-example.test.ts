import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; mesh: { vertices: number } | null; height_range: [number, number] | null };

describe("the noise terrain example", workBudget(240_000), () => {
  it("builds four joined tiles and a rock with commands only and renders them", () => {
    const out = freshDir("noise-terrain-example");
    const env = { ...process.env, BLENDWORKS_TERRAIN_RESOLUTION: "21", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/noise_terrain.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const tiles = log.filter((entry) => entry.cmd === "heightfield");
    expect(tiles).toHaveLength(4);
    for (const tile of tiles) expect(tile.mesh?.vertices).toBe(21 * 21 + 80);
    expect(log.filter((entry) => entry.cmd === "noise_displace")).toHaveLength(3);
    for (const name of ["overview", "overview-clay", "ridge-detail", "tile-joint", "rock"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "noise-terrain.blend"))).toBe(true);
  });
});
