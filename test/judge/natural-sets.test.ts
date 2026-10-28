import { writeFileSync } from "node:fs";
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

const SIZE_BAND = { min: -2.5, max: -1.5 };

let assets = "";
let specs = "";
const reports = new Map<string, Report>();
const passes = new Map<string, PassStage[][]>();

async function judged(name: string, asset: string, natural: Record<string, unknown>, views?: string[]): Promise<Report> {
  const specPath = join(specs, `${name}.spec.json`);
  writeFileSync(specPath, JSON.stringify({ name, format: "glb", natural, ...(views === undefined ? {} : { views }) }));
  const stages: PassStage[][] = [];
  const report = await judge({ specPath, assetPath: join(assets, `${asset}.glb`), outDir: join(specs, name), preview: views === undefined, afterPass: (ran) => stages.push(ran) });
  reports.set(name, report);
  passes.set(name, stages);
  return report;
}

function rule(name: string, ruleName: string) {
  return reports.get(name)!.rules.find((entry) => entry.rule === ruleName)!;
}

function natural(name: string) {
  return reports.get(name)!.measurements!.natural!;
}

beforeAll(
  withWorkBudget(400_000, async () => {
    assets = makeFixtureSet("natural_sets_fixtures", "natural-sets").assets;
    specs = freshDir("natural-sets", "specs");
    await judged("tiled", "tiled-plane", { class: "rock", repetition: { max: 0.8 } }, ["top"]);
    await judged("untiled", "untiled-plane", { class: "rock", repetition: { max: 0.8 } }, ["top"]);
    await judged("tiled-preview", "tiled-plane", { class: "rock", repetition: { max: 0.8 } });
    for (const asset of ["copies-identical", "copies-varied", "copies-realized", "copies-realized-varied"]) await judged(asset, asset, { class: "rock", instanceRepetition: {} });
    await judged("copies-other-objects", "copies-identical", { class: "rock", instanceRepetition: { objects: "Nothing*" } });
    for (const asset of ["leonardo-2", "leonardo-3", "leonardo-equal", "leonardo-none", "leonardo-v2", "leonardo-forged", "leonardo-forged-spanning", "leonardo-outside", "leonardo-toomany", "leonardo-format", "leonardo-sparse"]) {
      await judged(asset, asset, { class: "tree", leonardo: {} });
    }
    await judged("sizes-power", "sizes-power", { class: "rock", sizeDistribution: SIZE_BAND });
    await judged("sizes-uniform", "sizes-uniform", { class: "rock", sizeDistribution: SIZE_BAND });
    await judged("forest", "forest", { class: "tree", sizeDistribution: SIZE_BAND });
    await judged("forest-without-skeletons", "sizes-power", { class: "tree", sizeDistribution: SIZE_BAND });
  }),
);

describe("natural.repetition through the judge", workBudget(60_000), () => {
  it("fails an exactly tiled texture and passes an untiled one on the rendered views", () => {
    expect(rule("tiled", "natural.repetition")).toMatchObject({ pass: false, limit: { max: 0.8, source: "spec" } });
    expect(natural("tiled").repetition!.worst).toBeGreaterThan(0.8);
    expect(rule("untiled", "natural.repetition")).toMatchObject({ pass: true });
    expect(natural("untiled").repetition!.worst).toBeLessThan(0.3);
    expect(Object.keys(natural("tiled").repetition!.views)).toEqual(["top"]);
  });

  it("reports null and fails when the views did not render", () => {
    expect(rule("tiled-preview", "natural.repetition")).toMatchObject({ pass: false, measured: { worst: null, failure: expect.stringContaining("preview") } });
  });

  it("measures on the views of the one judge pass, with no extra stage", () => {
    expect(passes.get("tiled")).toEqual([["measure", "views", "sheet"]]);
    expect(passes.get("tiled-preview")).toEqual([["measure", "sheet"]]);
  });
});

describe("natural.instanceRepetition through the judge", workBudget(60_000), () => {
  it("gives 100 identical copies a share of 1.0, which fails the cited default", () => {
    expect(natural("copies-identical").instanceRepetition).toMatchObject({ share: 1, largestGroup: 100, pieces: 100, meshes: 1 });
    expect(rule("copies-identical", "natural.instanceRepetition")).toMatchObject({ pass: false, limit: { max: 0.1, source: "cited" } });
  });

  it("gives copies with random scale and yaw a share under 0.05", () => {
    expect(natural("copies-varied").instanceRepetition!.share).toBeLessThan(0.05);
    expect(rule("copies-varied", "natural.instanceRepetition").pass).toBe(true);
  });

  it("detects realized duplicates in one mesh like instances, by shape, scale and yaw", () => {
    expect(natural("copies-realized").instanceRepetition).toMatchObject({ share: 1, pieces: 100, meshes: 1 });
    expect(natural("copies-realized-varied").instanceRepetition).toMatchObject({ pieces: 100, meshes: 1 });
    expect(natural("copies-realized-varied").instanceRepetition!.share).toBeLessThan(0.05);
    expect(rule("copies-realized", "natural.instanceRepetition").pass).toBe(false);
    expect(rule("copies-realized-varied", "natural.instanceRepetition").pass).toBe(true);
  });

  it("reports null and fails when no object matches the pattern", () => {
    expect(rule("copies-other-objects", "natural.instanceRepetition")).toMatchObject({ pass: false, measured: { share: null }, limit: { objects: "Nothing*" } });
  });
});

describe("natural.leonardo through the judge", workBudget(60_000), () => {
  it("measures a median of 2 within 0.05 on a tree of tubes built with Δ = 2, which passes Eloy's range", () => {
    const measured = natural("leonardo-2").leonardo!;
    expect(Math.abs(measured.median! - 2)).toBeLessThan(0.05);
    expect(measured.measured).toBeGreaterThanOrEqual(15);
    expect(measured.branchings).toBe(20);
    expect(rule("leonardo-2", "natural.leonardo")).toMatchObject({ pass: true, limit: { min: 1.8, max: 2.3, source: "cited" } });
  });

  it("measures a median of 3 within 0.05 with Δ = 3, which fails it", () => {
    expect(Math.abs(natural("leonardo-3").leonardo!.median! - 3)).toBeLessThan(0.05);
    expect(rule("leonardo-3", "natural.leonardo").pass).toBe(false);
  });

  it("fails a tree of equal-radius tubes, although its skeleton says Δ = 2: the radii come from the mesh", () => {
    expect(natural("leonardo-equal").leonardo!.median).toBeGreaterThan(5);
    expect(rule("leonardo-equal", "natural.leonardo").pass).toBe(false);
  });

  it("reports null and fails without a skeleton, and refuses a skeleton of another version", () => {
    expect(rule("leonardo-none", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: "no object carries a blendworks.skeleton skeleton" } });
    expect(rule("leonardo-v2", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: expect.stringContaining("version 2; the judge reads version 1 only") } });
  });
});

describe("natural.leonardo with a hostile skeleton", workBudget(60_000), () => {
  it("fails a forged skeleton laid only over a Δ = 2 spot of a mesh whose other branches do not follow the rule", () => {
    expect(rule("leonardo-forged", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: expect.stringContaining("under 50% of the mesh") } });
  });

  it("fails a forged skeleton stretched over the mesh's extent that leaves most of the mesh unexplained", () => {
    expect(rule("leonardo-forged-spanning", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: expect.stringContaining("of the mesh surface lies within") } });
  });

  it("fails a skeleton whose nodes lie outside the mesh", () => {
    expect(rule("leonardo-outside", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: expect.stringContaining("lie inside the mesh") } });
  });

  it("fails a skeleton with fewer branchings than its size needs", () => {
    expect(rule("leonardo-sparse", "natural.leonardo")).toMatchObject({ pass: false, measured: { median: null, failure: expect.stringMatching(/the skeleton has 1 branchings, fewer than the \d+ its length/) } });
  });

  it("refuses an over-long skeleton before any work, and an unknown format", () => {
    expect(rule("leonardo-toomany", "natural.leonardo")).toMatchObject({ pass: false, measured: { failure: "Tree: the skeleton has 50001 nodes, over the judge's cap of 50000" } });
    expect(rule("leonardo-format", "natural.leonardo")).toMatchObject({ pass: false, measured: { failure: "Tree: the skeleton's format is not blendworks.skeleton" } });
  });
});

describe("natural.sizeDistribution through the judge", workBudget(60_000), () => {
  it("fits the bounding-sphere diameters of a power-law set near -2 and passes the band", () => {
    const sizes = natural("sizes-power").sizeDistribution!;
    expect(sizes).toMatchObject({ by: "sphere", count: 300 });
    expect(Math.abs(sizes.exponent! + 2)).toBeLessThan(0.2);
    expect(rule("sizes-power", "natural.sizeDistribution").pass).toBe(true);
  });

  it("fails a set of uniform sizes", () => {
    expect(rule("sizes-uniform", "natural.sizeDistribution").pass).toBe(false);
  });

  it("measures trees by trunk diameter on the mesh at breast height", () => {
    const sizes = natural("forest").sizeDistribution!;
    expect(sizes).toMatchObject({ by: "trunk", count: 150, unmeasured: 0 });
    expect(Math.abs(sizes.exponent! + 2)).toBeLessThan(0.25);
    expect(rule("forest", "natural.sizeDistribution").pass).toBe(true);
    expect(rule("forest-without-skeletons", "natural.sizeDistribution")).toMatchObject({ pass: false, measured: { exponent: null } });
  });
});

describe("the new natural values in the report", workBudget(60_000), () => {
  it("are in the summary and in blendworks diff", () => {
    const changes = diffReports(readReport(join(specs, "leonardo-2", "report.json")), readReport(join(specs, "leonardo-3", "report.json"))).map((change) => change.path);
    expect(changes).toContain("natural.leonardo.median");
    expect(changes).toContain("natural.leonardo");
    const sizes = diffReports(readReport(join(specs, "sizes-power", "report.json")), readReport(join(specs, "sizes-uniform", "report.json"))).map((change) => change.path);
    expect(sizes).toContain("natural.sizeDistribution.exponent");
    expect(reports.get("tiled")!.summary).toMatch(/natural: repetition worst 0\.\d+ in top/);
    expect(reports.get("copies-identical")!.summary).toMatch(/instance repetition 1 \(100 of 100 pieces alike\)/);
    expect(reports.get("leonardo-2")!.summary).toMatch(/Leonardo median delta 2/);
  });
});
