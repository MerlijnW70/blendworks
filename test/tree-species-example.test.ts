import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const SPECIES = ["oak", "birch", "pine", "willow", "maple", "olive"];

type Entry = {
  cmd: string;
  name?: string;
  preset?: string;
  species?: string;
  pipe_error?: number;
  manifold?: boolean;
  shells?: number;
  leaves?: number;
  clusters?: number;
  material?: string;
  variation?: Record<string, number>;
  strands?: { irregular?: boolean };
};

describe("the tree species example", workBudget(420_000), () => {
  it("grows, meshes and leafs the six species presets by commands only and renders each at mid and close range", () => {
    const out = freshDir("tree-species-example");
    const env = { ...process.env, BLENDWORKS_TREE_DETAIL: "0.25", BLENDWORKS_MEASURE_CROWNS: "0", BLENDWORKS_SHOT_SIZE: "96", BLENDWORKS_SHOT_SAMPLES: "2", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/tree_species.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const grown = log.filter((entry) => entry.cmd === "grow_tree");
    expect(grown.map((entry) => [entry.name, entry.preset, entry.species])).toEqual(SPECIES.map((species) => [species, species, species]));
    for (const entry of grown) expect(entry.pipe_error ?? 1, entry.name).toBeLessThan(1e-6);
    expect(grown.find((entry) => entry.name === "willow")?.strands?.irregular).toBe(true);
    const meshes = log.filter((entry) => entry.cmd === "tree_mesh");
    for (const mesh of meshes) {
      expect(mesh.manifold, mesh.name).toBe(true);
      expect(mesh.shells, mesh.name).toBe(1);
    }
    const leaves = log.filter((entry) => entry.cmd === "tree_leaves");
    expect(leaves.map((entry) => [entry.name, entry.species, entry.material])).toEqual(SPECIES.map((species) => [`${species}_leaves`, species, `${species}_leaf`]));
    for (const entry of leaves) {
      expect(entry.leaves ?? 0, entry.name).toBeGreaterThan(1_000);
      expect(entry.variation?.shapes ?? 0, entry.name).toBeGreaterThanOrEqual(3);
    }
    for (const species of SPECIES) {
      for (const view of ["mid", "close"]) {
        const path = join(out, `${species}_${view}.png`);
        expect(existsSync(path), path).toBe(true);
        expect(statSync(path).size, path).toBeGreaterThan(1_000);
      }
    }
  });
});
