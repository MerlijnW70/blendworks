import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { diffReports, readReport } from "../../src/judge/diff.js";
import type { PassStage } from "../../src/judge/onepass.js";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const EVERY_MEASURE = { silhouetteDimension: { min: 0 }, solidity: { max: 1 }, surfaceRoughness: { p90Min: 0 }, albedoVariation: { min: 0 } };

let assets = "";
let specs = "";
const reports = new Map<string, Report>();
const passes = new Map<string, PassStage[][]>();

async function judged(name: string, asset: string, natural: Record<string, unknown>): Promise<Report> {
  const specPath = join(specs, `${name}.spec.json`);
  writeFileSync(specPath, JSON.stringify({ name, format: "glb", natural }));
  const stages: PassStage[][] = [];
  const report = await judge({ specPath, assetPath: join(assets, `${asset}.glb`), outDir: join(specs, name), preview: true, afterPass: (ran) => stages.push(ran) });
  reports.set(name, report);
  passes.set(name, stages);
  return report;
}

function rule(report: Report, name: string) {
  return report.rules.find((entry) => entry.rule === name);
}

beforeAll(withWorkBudget(400_000, async () => {
  assets = makeFixtureSet("natural_fixtures", "natural").assets;
  specs = freshDir("natural", "specs");
  for (const asset of ["uv-sphere", "cube", "clouds-ico", "albedo-flat", "albedo-two-tone", "rough-rock", "card-opaque", "card-cutout"]) await judged(asset, asset, { class: "rock", ...EVERY_MEASURE });
  await judged("rock-defaults-pass", "rough-rock", { class: "rock", solidity: {}, surfaceRoughness: {}, albedoVariation: {} });
  await judged("rock-defaults-fail", "clouds-ico", { class: "rock", solidity: {}, surfaceRoughness: {}, albedoVariation: {} });
  await judged("flat-colour-fail", "albedo-flat", { class: "rock", albedoVariation: {} });
  await judged("foliage-pass", "leaf-cloud", { class: "plant", silhouetteDimension: { min: 1.4 } });
  await judged("foliage-fail", "cylinder-tree", { class: "plant", silhouetteDimension: { min: 1.4 } });
}));

describe("natural measures through the judge", workBudget(60_000), () => {
  it("measures a sphere as smooth: p90 under 5 degrees and a flat share above 0.9", () => {
    const roughness = reports.get("uv-sphere")!.measurements!.natural!.surfaceRoughness!;
    expect(roughness.lowestP90).toBeLessThan(5);
    expect(roughness.highestFlatShare).toBeGreaterThan(0.9);
  });

  it("measures a cube as flat: a flat share of 1 and a p90 of 0", () => {
    const roughness = reports.get("cube")!.measurements!.natural!.surfaceRoughness!;
    expect(roughness.highestFlatShare).toBe(1);
    expect(roughness.lowestP90).toBe(0);
  });

  it("gives an albedo CV of 0 for a constant-colour texture", () => {
    expect(reports.get("albedo-flat")!.measurements!.natural!.albedoVariation!.cv).toBe(0);
  });

  it("gives the hand-worked CV of a two-tone texture: a quarter at 0.2, the rest at 0.6", () => {
    const expected = (Math.sqrt(0.25 * 0.75) * (0.6 - 0.2)) / (0.25 * 0.2 + 0.75 * 0.6);
    const albedo = reports.get("albedo-two-tone")!.measurements!.natural!.albedoVariation!;
    expect(albedo.texels).toBe(64 * 64);
    expect(albedo.cv).toBeCloseTo(expected, 5);
  });

  it("reports a null albedo, which fails, when no base colour texture is on the faces", () => {
    const report = reports.get("clouds-ico")!;
    expect(report.measurements!.natural!.albedoVariation).toMatchObject({ cv: null, texels: 0, untexturedShare: 1 });
    expect(rule(report, "natural.albedoVariation")).toMatchObject({ measured: { cv: null }, pass: false });
  });

  it("measures the silhouettes of front, right and top at 1024 px, square and full for a cube", () => {
    const silhouettes = reports.get("cube")!.measurements!.natural!.silhouettes!;
    expect(Object.keys(silhouettes.views).sort()).toEqual(["front", "right", "top"]);
    expect(silhouettes.solidity).toBe(1);
    expect(silhouettes.dimension).toBeCloseTo(1, 1);
  });

  it("honours alpha cut-outs in the natural silhouettes: a card cut away on one half shows half its area", () => {
    const opaque = reports.get("card-opaque")!.measurements!.natural!.silhouettes!.views["front"]!.area;
    const cutout = reports.get("card-cutout")!.measurements!.natural!.silhouettes!.views["front"]!.area;
    expect(opaque).toBeGreaterThan(10_000);
    expect(cutout / opaque).toBeCloseTo(0.5, 1);
    expect(reports.get("card-cutout")!.measurements!.natural!.albedoVariation!.texels).toBe(64 * 32);
  });

  it("keeps each natural silhouette beside the report, with its sha256 in the measurements", () => {
    const silhouettes = reports.get("cube")!.measurements!.natural!.silhouettes!;
    for (const view of ["front", "right", "top"]) {
      const data = readFileSync(join(specs, "cube", "natural", `${view}-silhouette.png`));
      expect(createHash("sha256").update(data).digest("hex")).toBe(silhouettes.views[view]!.sha256);
    }
  });

  it("measures everything in the one judge pass, with the silhouettes in the reference stage", () => {
    for (const [name, stages] of passes) expect(stages, name).toEqual([name === "flat-colour-fail" ? ["measure", "sheet"] : ["measure", "reference", "sheet"]]);
    expect(reports.get("cube")!.timings.reference).toBeGreaterThan(0);
  });
});

describe("natural rules with their calibrated defaults", workBudget(60_000), () => {
  it("pass a rough, concave, textured rock and fail the clouds-displaced ico sphere", () => {
    const passing = reports.get("rock-defaults-pass")!;
    const failing = reports.get("rock-defaults-fail")!;
    for (const name of ["natural.solidity", "natural.surfaceRoughness", "natural.albedoVariation"]) {
      expect(rule(passing, name), name).toMatchObject({ pass: true, limit: { class: "rock", source: "calibrated" } });
      expect(rule(failing, name)?.pass, name).toBe(false);
    }
    expect(passing.passed).toBe(true);
    expect(failing.passed).toBe(false);
  });

  it("fail the clouds-displaced ico sphere on the calibrated rock roughness", () => {
    expect(rule(reports.get("rock-defaults-fail")!, "natural.surfaceRoughness")).toMatchObject({ pass: false, limit: { source: "calibrated" } });
  });

  it("fail a constant-colour texture on the calibrated albedo variation", () => {
    expect(rule(reports.get("flat-colour-fail")!, "natural.albedoVariation")).toMatchObject({ measured: { cv: 0 }, pass: false });
  });

  it("pass a cloud of leaves and fail a cylinder tree on a silhouette dimension of at least 1.4, which the calibration leaves to the spec", () => {
    expect(rule(reports.get("foliage-pass")!, "natural.silhouetteDimension")?.pass).toBe(true);
    expect(rule(reports.get("foliage-fail")!, "natural.silhouetteDimension")?.pass).toBe(false);
  });

  it("put the values in the report, the summary and blendworks diff", () => {
    const passing = join(specs, "rock-defaults-pass", "report.json");
    const failing = join(specs, "rock-defaults-fail", "report.json");
    const changes = diffReports(readReport(passing), readReport(failing));
    const paths = changes.map((change) => change.path);
    expect(paths).toContain("natural.silhouettes.solidity");
    expect(paths).toContain("natural.surfaceRoughness.lowestP90");
    expect(paths).toContain("natural.albedoVariation.cv");
    expect(paths).toContain("natural.solidity");
    expect(reports.get("rock-defaults-pass")!.summary).toMatch(/natural: silhouettes 1024 px: front D \d/);
  });
});
