import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { PassStage } from "../../src/judge/onepass.js";
import { judge } from "../../src/judge/run.js";
import { maskFrom, maskImage } from "../../src/judge/silhouette.js";
import { encodePng } from "../../src/judge/visual/png.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";
import { answer, answering, BRIEF, RULE } from "./visual-helpers.js";

useBlenderSlot();

let assets = "";

beforeAll(withWorkBudget(120_000, () => {
  assets = makeFixtureSet("visual_fixtures", "one-process").assets;
}));

function spec(dir: string): string {
  const mask = encodePng(maskImage(maskFrom(64, 64, (x, y) => x >= 8 && x < 56 && y >= 14 && y < 50)));
  writeFileSync(join(dir, "front.png"), mask);
  const path = join(dir, "spec.json");
  const reference = { views: { front: { mask: "front.png", sha256: createHash("sha256").update(mask).digest("hex") } }, minIoU: 0.1 };
  writeFileSync(path, JSON.stringify({ name: "crate", format: "glb", triangles: { max: 800 }, views: ["front", "three-quarter"], brief: BRIEF, visual: RULE, reference }));
  return path;
}

async function passes(name: string, preview: boolean) {
  const dir = freshDir("one-process", name);
  const seen: PassStage[][] = [];
  const client = answering([answer([0.9, 0.8]), answer([0.9, 0.8]), answer([0.9, 0.8])]);
  const report = await judge({
    specPath: spec(dir),
    assetPath: join(assets, "crate-clean.glb"),
    outDir: join(dir, "out"),
    preview,
    afterPass: (stages) => seen.push(stages),
    visual: { anthropicClient: client, env: {}, credentials: async () => true, closeupResolution: 64, closeupSamples: 2 },
  });
  return { report, seen };
}

describe("one judge run", workBudget(120_000), () => {
  it("measures, makes the silhouettes, renders the views, the sheet and the close-ups in one Blender process", async () => {
    const { report, seen } = await passes("full", false);
    expect(seen).toEqual([["measure", "reference", "views", "sheet", "closeups"]]);
    expect(report.failure).toBeNull();
    expect(report.renders?.status).toBe("rendered");
    expect(report.reference?.views.map((view) => view.view)).toEqual(["front"]);
    expect(report.visual?.status).not.toBe("inconclusive");
    expect(Object.keys(report.timings)).toEqual(expect.arrayContaining(["measure", "reference", "render", "sheet", "closeups"]));
  });

  it("measures, makes the silhouettes and draws the sheet in one Blender process in preview mode", async () => {
    const { report, seen } = await passes("preview", true);
    expect(seen).toEqual([["measure", "reference", "sheet"]]);
    expect(report.renders?.status).toBe("preview");
    expect(report.reference?.views).toHaveLength(1);
  });
});
