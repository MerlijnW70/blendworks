import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = {
  cmd: string;
  name?: string;
  method?: string;
  nodes?: number;
  skeletons?: string[];
  lsystem?: { preset: string; organ_groups: Record<string, number>; segments: number };
};

describe("the L-system plants example", workBudget(240_000), () => {
  it("grows a herb, three stochastic bushes, a parametric tree and a compound leaf from the book's presets and renders them", () => {
    const out = freshDir("lsystem-plants-example");
    const env = { ...process.env, BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/lsystem_plants.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const plants = log.filter((entry) => entry.cmd === "lsystem");
    expect(plants.map((entry) => [entry.name, entry.lsystem?.preset])).toEqual([
      ["herb", "bush_1_25"],
      ["bush_1", "stochastic_1_27_leafy"],
      ["bush_2", "stochastic_1_27_leafy"],
      ["bush_3", "stochastic_1_27_leafy"],
      ["tree", "monopodial_2_6a"],
      ["fern", "compound_leaf_5_11b"],
    ]);
    for (const plant of plants) {
      expect(plant.method, plant.name).toBe("lsystem");
      expect(plant.nodes ?? 0, plant.name).toBeGreaterThan(200);
      expect(Object.values(plant.lsystem?.organ_groups ?? {}).reduce((sum, count) => sum + count, 0), plant.name).toBeGreaterThan(5);
    }
    const bushes = plants.filter((entry) => entry.name?.startsWith("bush_"));
    expect(new Set(bushes.map((entry) => entry.nodes)).size).toBeGreaterThan(1);
    expect(log.filter((entry) => entry.cmd === "material_procedural").length).toBeGreaterThanOrEqual(7);
    expect(log.find((entry) => entry.cmd === "export")?.skeletons).toEqual(["bush_1", "bush_2", "bush_3", "fern", "herb", "tree"]);
    for (const name of ["herb", "bushes", "tree", "fern", "overview"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(existsSync(join(out, "lsystem-plants.blend"))).toBe(true);
    expect(statSync(join(out, "lsystem-plants.glb")).size).toBeGreaterThan(10_000);
  });
});
