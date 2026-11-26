import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const SPECIES = ["oak", "birch", "pine", "willow", "maple", "olive"];
const reports = new Map<string, Report>();

beforeAll(
  withWorkBudget(840_000, async () => {
    const assets = makeFixtureSet("tree_species_fixtures", "tree-species").assets;
    const specs = freshDir("tree-species", "specs");
    const runs: [string, Record<string, unknown>, boolean][] = [
      ["linked", { leonardo: {}, repetition: {} }, false],
      ["barks", { leonardo: {}, surfaceRoughness: {} }, true],
    ];
    for (const [asset, natural, preview] of runs) {
      const specPath = join(specs, `${asset}.spec.json`);
      writeFileSync(specPath, JSON.stringify({ name: asset, format: "glb", natural: { class: "tree", ...natural } }));
      reports.set(asset, await judge({ specPath, assetPath: join(assets, `${asset}.glb`), outDir: join(specs, asset), preview }));
    }
  }),
);

function rule(asset: string, name: string) {
  const found = reports.get(asset)!.rules.find((entry) => entry.rule === name);
  expect(found, `${asset} ${name}`).toBeDefined();
  return found!;
}

describe("the six species presets through the full judge", workBudget(60_000), () => {
  it("keep the tree repetition default and Leonardo's rule on a shipped preset with its eight linked cluster variants", () => {
    expect(rule("linked", "natural.leonardo").pass).toBe(true);
    expect(rule("linked", "natural.repetition").pass).toBe(true);
  });

  it("keep the calibrated tree surface roughness on every species' bark", () => {
    const roughness = reports.get("barks")!.measurements!.natural!.surfaceRoughness!;
    const leonardo = reports.get("barks")!.measurements!.natural!.leonardo!;
    expect(leonardo.failure).toBeNull();
    expect(new Set(leonardo.skeletons.map((entry) => entry.object.replace(/_bark$/, "")))).toEqual(new Set(SPECIES));
    expect(roughness.objects).toBe(SPECIES.length);
    expect(rule("barks", "natural.surfaceRoughness").pass).toBe(true);
    expect(rule("barks", "natural.leonardo").pass).toBe(true);
  });
});
