import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; name?: string; skeletons?: string[]; manifold?: boolean; shells?: number; self_intersections?: number; volume?: number; materials?: string[]; leaves?: number; tip_leaves?: number; skeleton?: { nodes: number } };

const SHOTS = ["oak", "conifer", "windswept", "row", "oak_base", "oak_bark", "oak_fork", "conifer_bark", "windswept_base"];

describe("the tree meshes example", workBudget(300_000), () => {
  it("turns the three grown skeletons into closed bark meshes with leaves by commands only and renders them", () => {
    const out = freshDir("tree-meshes-example");
    const env = { ...process.env, BLENDWORKS_TREE_DETAIL: "0.3", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/tree_meshes.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const meshes = log.filter((entry) => entry.cmd === "tree_mesh");
    expect(meshes.map((entry) => entry.name)).toEqual(["oak_bark", "conifer_bark", "windswept_bark"]);
    for (const mesh of meshes) {
      expect(mesh.manifold, mesh.name).toBe(true);
      expect(mesh.shells, mesh.name).toBe(1);
      expect(mesh.self_intersections, mesh.name).toBe(0);
      expect(mesh.volume ?? 0, mesh.name).toBeGreaterThan(0);
      expect(mesh.materials, mesh.name).toContain("bark");
      expect(mesh.skeleton?.nodes ?? 0, mesh.name).toBeGreaterThan(200);
    }
    const leaves = log.filter((entry) => entry.cmd === "tree_leaves");
    expect(leaves.map((entry) => entry.name)).toEqual(["oak_leaves", "conifer_leaves", "windswept_leaves"]);
    for (const entry of leaves) expect(entry.leaves ?? 0, entry.name).toBeGreaterThan(200);
    for (const name of SHOTS) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(log.find((entry) => entry.cmd === "export")?.skeletons).toEqual(["conifer_bark", "oak_bark", "windswept_bark"]);
    expect(existsSync(join(out, "tree-meshes.blend"))).toBe(true);
    expect(statSync(join(out, "tree-meshes.glb")).size).toBeGreaterThan(100_000);
  });
});
