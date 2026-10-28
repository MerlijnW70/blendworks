import { execFileSync } from "node:child_process";
import { existsSync, statSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; skeletons?: string[]; name?: string; method?: string; nodes?: number; root_nodes?: number; height?: number; pipe_error?: number };

describe("the grow trees example", workBudget(240_000), () => {
  it("grows an oak, a conifer and a windswept tree with roots by commands only and renders them", () => {
    const out = freshDir("grow-trees-example");
    const env = { ...process.env, BLENDWORKS_TREE_DETAIL: "0.3", BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "docs/examples/grow_trees.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    const trees = log.filter((entry) => entry.cmd === "grow_tree");
    expect(trees.map((entry) => [entry.name, entry.method])).toEqual([
      ["oak", "colonization"],
      ["conifer", "levels"],
      ["windswept", "colonization"],
    ]);
    for (const tree of trees) {
      expect(tree.nodes ?? 0, tree.name).toBeGreaterThan(200);
      expect(tree.root_nodes ?? 0, tree.name).toBeGreaterThan(20);
      expect(tree.pipe_error ?? 1, tree.name).toBeLessThan(1e-6);
    }
    for (const name of ["oak", "conifer", "windswept", "oak_top", "conifer_top", "oak_base", "row"]) {
      const path = join(out, `${name}.png`);
      expect(existsSync(path), name).toBe(true);
      expect(statSync(path).size, name).toBeGreaterThan(1_000);
    }
    expect(log.find((entry) => entry.cmd === "export")?.skeletons).toEqual(["conifer", "oak", "windswept"]);
    expect(existsSync(join(out, "grow-trees.blend"))).toBe(true);
    expect(statSync(join(out, "grow-trees.glb")).size).toBeGreaterThan(10_000);
  });
});
