import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Summary = {
  lake?: { level: number; area: number; max_depth: number; wind: { source: string }; shore: { objects: string[] } };
  river?: { length: number; joins: string | null };
  rocks?: { count: number; highest_above_water: number; deepest_under_water: number; wet: { objects: string[] } };
  cameras?: string[];
  render: { liquids: { objects: string[]; caustics: boolean } | null };
  commands: { cmd: string }[];
};

const SMALL = {
  BLENDWORKS_SHOT_WIDTH: "64",
  BLENDWORKS_SHOT_HEIGHT: "36",
  BLENDWORKS_SHOT_SAMPLES: "2",
  BLENDWORKS_SHOT_SECONDS: "60",
  BLENDWORKS_TREE_DETAIL: "0.05",
  BLENDWORKS_TREES: "1",
  BLENDWORKS_COVER_BUDGET: "3000",
  BLENDWORKS_CLOUD_FORM: "sheet",
  BLENDWORKS_LATHE_SEGMENTS: "24",
  BLENDWORKS_DEVICE: "cpu",
};

function run(script: string, name: string): { out: string; summary: Summary } {
  const out = freshDir(name);
  execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", script, "--", out], { env: { ...process.env, ...SMALL }, stdio: "pipe" });
  return { out, summary: JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary };
}

describe("the liquid scene examples", workBudget(900_000), () => {
  it("builds the lake scene by commands only: a river into a lake with stones at the water line, cover, trees, hills and fair cumulus", () => {
    const { out, summary } = run("docs/examples/liquid_lake.py", "liquid-lake-example");
    const used = new Set(summary.commands.map((entry) => entry.cmd));
    for (const command of ["heightfield", "noise_displace", "weather", "liquid_body", "shore_stones", "grow_tree", "tree_mesh", "tree_leaves", "ground_cover", "atmosphere", "render_final"]) expect(used.has(command), command).toBe(true);
    for (const command of ["set_world_hdri", "library_apply", "import", "run_python"]) expect(used.has(command), command).toBe(false);
    expect(summary.lake!.area).toBeGreaterThan(1000);
    expect(summary.lake!.max_depth).toBeGreaterThan(1);
    expect(summary.lake!.wind.source).toContain("weather");
    expect(summary.lake!.shore.objects).toContain("land");
    expect(summary.river!.joins).toBe("water");
    expect(summary.river!.length).toBeGreaterThan(60);
    expect(summary.rocks!.count).toBeGreaterThan(50);
    expect(summary.rocks!.highest_above_water).toBeLessThan(5);
    expect(summary.rocks!.deepest_under_water).toBeLessThan(1.5);
    expect(summary.rocks!.wet.objects.length).toBeGreaterThan(0);
    expect(summary.cameras).toEqual(["eye", "shore"]);
    expect(statSync(join(out, "rocks.png")).size).toBeGreaterThan(500);
    expect(summary.render.liquids!.caustics).toBe(false);
    expect(summary.render.liquids!.objects).toEqual(expect.arrayContaining(["lake", "river"]));
    expect(statSync(join(out, "lake.png")).size).toBeGreaterThan(500);
    expect(existsSync(join(out, "liquid-lake.blend"))).toBe(true);
  });

  it("builds the still life by commands only: water, wine, milk, oil, honey and spilled coffee on a wooden table", () => {
    const { out, summary } = run("docs/examples/liquid_still_life.py", "liquid-still-life-example");
    const used = new Set(summary.commands.map((entry) => entry.cmd));
    for (const command of ["lathe", "liquid_fill", "material_procedural", "render_final"]) expect(used.has(command), command).toBe(true);
    for (const command of ["set_world_hdri", "library_apply", "import", "run_python"]) expect(used.has(command), command).toBe(false);
    expect(summary.render.liquids!.objects).toEqual(expect.arrayContaining(["water", "wine", "milk", "oil", "honey", "coffee"]));
    expect(statSync(join(out, "still-life.png")).size).toBeGreaterThan(500);
    expect(statSync(join(out, "spill.png")).size).toBeGreaterThan(500);
  });

  it("builds a row of jars of honey, one for each USDA colour class", () => {
    const { out, summary } = run("docs/examples/liquid_honey_classes.py", "liquid-honey-example");
    const used = summary.commands.filter((entry) => entry.cmd === "liquid_fill").length;
    expect(used).toBe(7);
    expect(summary.render.liquids!.objects.filter((name) => name.startsWith("honey_"))).toHaveLength(7);
    expect(statSync(join(out, "honey.png")).size).toBeGreaterThan(500);
  });
});
