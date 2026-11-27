import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { type: string; matrix: string; counts?: number[]; data?: Record<string, string> };
type Digest = { objects: Record<string, Entry> };

function build(threads: number): Digest {
  const out = freshDir(`thread-scene-${threads}`);
  execFileSync(blenderPath(), ["--background", "--factory-startup", "--threads", String(threads), "--python", "bench/thread-scene/scene.py", "--", out], { stdio: "pipe" });
  return JSON.parse(readFileSync(join(out, "digest.json"), "utf8")) as Digest;
}

function differing(a: Digest, b: Digest): string[] {
  const names = new Set([...Object.keys(a.objects), ...Object.keys(b.objects)]);
  return [...names].filter((name) => JSON.stringify(a.objects[name]) !== JSON.stringify(b.objects[name])).sort();
}

describe("the thread scene", workBudget(420_000), () => {
  it("builds the same geometry and attributes, sharp edges and edge order included, at 1, 4 and 32 threads", () => {
    const one = build(1);
    expect(Object.keys(one.objects).length).toBeGreaterThan(20);
    for (const name of ["land", "lake", "river", "glass", "birch_bark", "sheet", "ball", "ring", "drop"]) {
      const data = one.objects[name]?.data ?? {};
      expect(data["EDGE:.edge_verts"], name).toBeDefined();
      expect(data["CORNER:.corner_edge"], name).toBeDefined();
    }
    expect(one.objects["land"]?.data?.["EDGE:sharp_edge"]).toBeDefined();
    for (const threads of [4, 32]) {
      expect(differing(one, build(threads)), `objects that differ at ${threads} threads`).toEqual([]);
    }
  });
});
