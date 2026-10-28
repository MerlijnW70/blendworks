import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const NATURAL = { class: "rock", solidity: {}, surfaceRoughness: {}, albedoVariation: {} };
const RULES = ["natural.solidity", "natural.surfaceRoughness", "natural.albedoVariation"];
const reports = new Map<string, Report>();

function rule(report: Report, name: string) {
  return report.rules.find((entry) => entry.rule === name);
}

beforeAll(withWorkBudget(300_000, async () => {
  const assets = makeFixtureSet("rocks_fixtures", "rocks").assets;
  const specs = freshDir("rocks", "specs");
  for (const asset of ["FracturedRock", "DisplacedSphere"]) {
    const specPath = join(specs, `${asset}.spec.json`);
    writeFileSync(specPath, JSON.stringify({ name: asset, format: "glb", natural: NATURAL }));
    reports.set(asset, await judge({ specPath, assetPath: join(assets, `${asset}.glb`), outDir: join(specs, asset), preview: true }));
  }
}));

describe("rocks through the natural judge rules", workBudget(60_000), () => {
  it("passes the calibrated rock defaults for a rock built by fracture, chip, abrade and noise_displace", () => {
    const report = reports.get("FracturedRock")!;
    for (const name of RULES) expect(rule(report, name), name).toMatchObject({ pass: true, limit: { class: "rock", source: "calibrated" } });
    expect(report.passed).toBe(true);
  });

  it("fails a plain displaced sphere on solidity and roughness", () => {
    const report = reports.get("DisplacedSphere")!;
    expect(rule(report, "natural.solidity")?.pass).toBe(false);
    expect(rule(report, "natural.surfaceRoughness")?.pass).toBe(false);
    expect(report.passed).toBe(false);
  });
});
