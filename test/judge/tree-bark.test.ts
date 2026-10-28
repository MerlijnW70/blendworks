import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { NATURAL_DEFAULTS } from "../../src/judge/natural-defaults.js";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const reports = new Map<string, Report>();

beforeAll(
  withWorkBudget(400_000, async () => {
    const assets = makeFixtureSet("tree_bark_fixtures", "tree-bark").assets;
    const specs = freshDir("tree-bark", "specs");
    for (const asset of ["oak-bark", "cylinder-tree"]) {
      const specPath = join(specs, `${asset}.spec.json`);
      writeFileSync(specPath, JSON.stringify({ name: asset, format: "glb", natural: { class: "tree", surfaceRoughness: {} } }));
      reports.set(asset, await judge({ specPath, assetPath: join(assets, `${asset}.glb`), outDir: join(specs, asset), preview: true }));
    }
  }),
);

function roughness(asset: string) {
  return reports.get(asset)!.rules.find((rule) => rule.rule === "natural.surfaceRoughness")!;
}

describe("the bark mesh of the example oak through the full judge", workBudget(60_000), () => {
  it("passes natural.surfaceRoughness with the calibrated tree default", () => {
    const rule = roughness("oak-bark");
    expect(rule.limit).toEqual({ ...NATURAL_DEFAULTS.tree.surfaceRoughness, class: "tree", source: "calibrated" });
    expect(rule.pass).toBe(true);
    const measured = reports.get("oak-bark")!.measurements!.natural!.surfaceRoughness!;
    expect(measured.highestFlatShare).toBeLessThan(NATURAL_DEFAULTS.tree.surfaceRoughness!.flatShareMax!);
  });

  it("while a tree built from plain cylinders fails it", () => {
    const rule = roughness("cylinder-tree");
    expect(rule.pass).toBe(false);
    const measured = reports.get("cylinder-tree")!.measurements!.natural!.surfaceRoughness!;
    expect(measured.highestFlatShare).toBeGreaterThan(NATURAL_DEFAULTS.tree.surfaceRoughness!.flatShareMax!);
  });
});
