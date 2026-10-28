import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Form = { kinks: number; largest_gnarl: number; pruned: number; largest_sag_curvature?: number };
type Entry = {
  cmd: string;
  name?: string;
  preset?: string;
  method?: string;
  pipe_error?: number;
  nodes?: number;
  spread?: number;
  growth?: { form?: Form };
  skeletons?: string[];
  manifold?: boolean;
  shells?: number;
  volume?: number;
  leaves?: number;
};

const SHOTS = ["willow", "oak", "coastal", "row", "oak_trunk"];

describe("the tree shapes example", workBudget(300_000), () => {
  it("grows, meshes and leafs a weeping willow, a gnarled oak and a wind-bent coastal tree by commands only and renders them", () => {
    const out = freshDir("tree-shapes-example");
    const env = { ...process.env, BLENDWORKS_TREE_DETAIL: "0.3", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/tree_shapes.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const grown = log.filter((entry) => entry.cmd === "grow_tree");
    expect(grown.map((entry) => [entry.name, entry.preset, entry.method])).toEqual([
      ["willow", "weeping_willow", "levels"],
      ["oak", "gnarled_oak", "colonization"],
      ["coastal", "windswept_coastal", "colonization"],
    ]);
    for (const entry of grown) {
      expect(entry.pipe_error ?? 1, entry.name).toBeLessThan(1e-6);
      expect(entry.growth?.form, entry.name).toBeDefined();
    }
    const oak = grown[1]!.growth!.form!;
    expect(oak.kinks).toBeGreaterThan(20);
    expect(oak.largest_gnarl).toBeGreaterThan(0.1);
    expect(oak.largest_sag_curvature ?? 0).toBeGreaterThan(0);
    const meshes = log.filter((entry) => entry.cmd === "tree_mesh");
    expect(meshes.map((entry) => entry.name)).toEqual(["willow_bark", "oak_bark", "coastal_bark"]);
    for (const mesh of meshes) {
      expect(mesh.manifold, mesh.name).toBe(true);
      expect(mesh.shells, mesh.name).toBe(1);
      expect(mesh.volume ?? 0, mesh.name).toBeGreaterThan(0);
    }
    const leaves = log.filter((entry) => entry.cmd === "tree_leaves");
    expect(leaves.map((entry) => entry.name)).toEqual(["willow_leaves", "oak_leaves", "coastal_leaves"]);
    for (const entry of leaves) expect(entry.leaves ?? 0, entry.name).toBeGreaterThan(500);
    for (const name of SHOTS) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(log.find((entry) => entry.cmd === "export")?.skeletons).toEqual(["coastal_bark", "oak_bark", "willow_bark"]);
    expect(statSync(join(out, "tree-shapes.glb")).size).toBeGreaterThan(100_000);
  });
});
