import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Skeleton = {
  format: string;
  version: number;
  units: string;
  space: string;
  up: string;
  method: string;
  exponent: number;
  tip_radius: number;
  count: number;
  position: number[];
  parent: number[];
  radius: number[];
  order: number[];
  kind: number[];
};

type GltfNode = { name?: string; extras?: { blendworks_skeleton?: Skeleton } };

function readGlbJson(path: string): { nodes?: GltfNode[] } {
  const data = readFileSync(path);
  expect(data.readUInt32LE(0)).toBe(0x46546c67);
  expect(data.readUInt32LE(8)).toBe(data.length);
  const length = data.readUInt32LE(12);
  expect(data.readUInt32LE(16)).toBe(0x4e4f534a);
  return JSON.parse(data.subarray(20, 20 + length).toString("utf8")) as { nodes?: GltfNode[] };
}

function skeletonsIn(path: string): Map<string, Skeleton> {
  const found = new Map<string, Skeleton>();
  for (const node of readGlbJson(path).nodes ?? []) {
    const skeleton = node.extras?.blendworks_skeleton;
    if (skeleton !== undefined && node.name !== undefined) found.set(node.name, skeleton);
  }
  return found;
}

let assets = "";

beforeAll(
  withWorkBudget(240_000, () => {
    assets = freshDir("tree-skeleton-extras");
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "test/tree_skeleton_fixture.py", "--", assets], { stdio: "pipe" });
  }),
);

describe("tree skeletons in glTF extras", workBudget(60_000), () => {
  it("carry every node of the grown skeleton, read as plain glTF JSON", () => {
    const skeletons = skeletonsIn(join(assets, "trees.glb"));
    const expected = JSON.parse(readFileSync(join(assets, "trees.expected.json"), "utf8")) as Record<string, Skeleton>;
    expect([...skeletons.keys()].sort()).toEqual(["broadleaf", "conifer"]);
    for (const [name, skeleton] of skeletons) {
      expect(skeleton).toEqual(expected[name]);
    }
  });

  it("follow the documented version 1 layout: one root, parents first, roots below the base", () => {
    const skeletons = skeletonsIn(join(assets, "trees.glb"));
    expect(skeletons.size).toBe(2);
    for (const [name, skeleton] of skeletons) {
      expect(skeleton.format).toBe("blendworks.skeleton");
      expect(skeleton.version).toBe(1);
      expect([skeleton.units, skeleton.space, skeleton.up]).toEqual(["metre", "object", "z"]);
      const count = skeleton.count;
      expect(count).toBeGreaterThan(100);
      for (const column of [skeleton.parent, skeleton.radius, skeleton.order, skeleton.kind]) expect(column).toHaveLength(count);
      expect(skeleton.position).toHaveLength(3 * count);
      expect(skeleton.parent[0]).toBe(-1);
      const baseZ = skeleton.position[2] ?? 0;
      const sums = new Array<number>(count).fill(0);
      const childCount = new Array<number>(count).fill(0);
      for (let node = 1; node < count; node += 1) {
        const parent = skeleton.parent[node] ?? -1;
        expect(parent, `${name} node ${node}`).toBeGreaterThanOrEqual(0);
        expect(parent, `${name} node ${node}`).toBeLessThan(node);
        const z = skeleton.position[3 * node + 2] ?? 0;
        if (skeleton.kind[node] === 1) expect(z).toBeLessThan(baseZ);
        else expect(z).toBeGreaterThan(baseZ);
        sums[parent] = (sums[parent] ?? 0) + (skeleton.radius[node] ?? 0) ** skeleton.exponent;
        childCount[parent] = (childCount[parent] ?? 0) + 1;
      }
      let branchings = 0;
      for (let node = 0; node < count; node += 1) {
        if ((childCount[node] ?? 0) < 2) continue;
        branchings += 1;
        const own = (skeleton.radius[node] ?? 0) ** skeleton.exponent;
        expect(Math.abs(own - (sums[node] ?? 0)) / own).toBeLessThan(1e-6);
      }
      expect(branchings).toBeGreaterThan(20);
    }
  });
});
