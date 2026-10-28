import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; mesh: { vertices: number } | null };
type Summary = { erosion: { eroded_volume: number; deposited_volume: number; carried_off_volume: number; edge_change: number; grid: number[]; tiles: string[] }; commands: Entry[] };

describe("the eroded terrain example", workBudget(240_000), () => {
  it("erodes four joined tiles together, dresses them with attribute masks and renders them", () => {
    const out = freshDir("eroded-terrain-example");
    const env = { ...process.env, BLENDWORKS_TERRAIN_RESOLUTION: "21", BLENDWORKS_DROPLETS: "400", BLENDWORKS_SWEEPS: "20", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/eroded_terrain.py", "--", out], { env, stdio: "pipe" });
    const summary = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary;
    const tiles = summary.commands.filter((entry) => entry.cmd === "heightfield");
    expect(tiles).toHaveLength(4);
    for (const tile of tiles) expect(tile.mesh?.vertices).toBe(21 * 21);
    expect(summary.commands.filter((entry) => entry.cmd === "erode")).toHaveLength(1);
    expect(summary.erosion.tiles).toHaveLength(4);
    expect(summary.erosion.grid).toEqual([41, 41]);
    expect(summary.erosion.edge_change).toBe(0);
    expect(summary.erosion.eroded_volume).toBeGreaterThan(0);
    expect(summary.erosion.deposited_volume).toBeGreaterThan(0);
    expect(summary.commands.filter((entry) => entry.cmd === "material_nodes")).toHaveLength(1);
    for (const name of ["overview", "overview-clay", "channels", "channels-clay", "tile-joint-clay"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "eroded-terrain.blend"))).toBe(true);
  });
});
