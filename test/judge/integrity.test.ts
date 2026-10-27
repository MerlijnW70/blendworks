import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(() => {
  ({ assets } = makeFixtureSet("integrity_fixtures", "integrity"));
  specs = freshDir("integrity", "specs");
}, 180_000);

async function judged(asset: string, rules: Record<string, unknown>, label: string): Promise<Report> {
  const name = `${asset.replace(/\W+/g, "-")}-${label}`;
  const spec = join(specs, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ format: asset.split(".").pop(), views: ["front"], ...rules }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("integrity", "reports", name), preview: true });
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

async function caughtOnlyBy(asset: string, rules: Record<string, unknown>, guard: Record<string, unknown>, expected: string[]): Promise<Report> {
  const guarded = await judged(asset, { ...rules, ...guard }, "guarded");
  expect(guarded.failure).toBeNull();
  expect(failing(guarded)).toEqual(expected);
  const unguarded = await judged(asset, rules, "unguarded");
  expect(failing(unguarded)).toEqual([]);
  expect(unguarded.passed).toBe(true);
  return guarded;
}

describe("gaming fixtures fail their rule, and pass once the rule is removed", { timeout: 180_000 }, () => {
  it("a crate padded with 20 hidden 0.1 m cubes: 252 triangles, only the 12 of the crate visible, 1.2 of 6.4 m2 hidden", async () => {
    const report = await caughtOnlyBy("padded.glb", { triangles: { min: 100 } }, { triangles: { min: 100, minVisible: 100 }, faces: { maxHiddenRatio: 0.1 } }, [
      "triangles.minVisible",
      "faces.maxHiddenRatio",
    ]);
    expect(report.measurements?.triangles).toBe(252);
    expect(report.measurements?.visibleTriangles).toBe(12);
    expect(report.measurements?.faces).toMatchObject({ hiddenRatio: 0.1875, hiddenFaces: 240, tested: 252, sampled: false });
    expect(report.measurements?.shells).toEqual({ count: 21, closed: 21, inverted: 0 });
  });

  it("a crate with a zero-area triangle of three points on one line", async () => {
    const report = await caughtOnlyBy("degenerate.glb", {}, { faces: { maxDegenerate: 0 } }, ["faces.maxDegenerate"]);
    expect(report.measurements?.faces.degenerate).toBe(1);
    expect(report.measurements?.triangles).toBe(13);
    expect(report.measurements?.visibleTriangles).toBe(12);
  });

  it("a crate with a second lid on the same four corners", async () => {
    const report = await caughtOnlyBy("duplicate.blend", {}, { faces: { maxDuplicate: 0 } }, ["faces.maxDuplicate"]);
    expect(report.measurements?.faces.duplicate).toBe(1);
  });

  it("a crate turned inside out: closed, manifold, and its signed volume negative", async () => {
    const report = await caughtOnlyBy("inverted.glb", { manifold: true }, { manifold: { required: true, noInverted: true } }, ["manifold.noInverted"]);
    expect(report.measurements?.shells).toEqual({ count: 1, closed: 1, inverted: 1 });
    expect(report.rules.find((rule) => rule.rule === "manifold")?.pass).toBe(true);
  });

  it("a crate with four 1 cm specks on its lid: five closed shells", async () => {
    const report = await caughtOnlyBy("tiny-shells.glb", { manifold: true }, { shells: { max: 1 } }, ["shells.max"]);
    expect(report.measurements?.shells).toEqual({ count: 5, closed: 5, inverted: 0 });
  });

  it("a loose vertex 5 m away and a 3 m wire edge change neither size nor origin, and fail manifold", async () => {
    const report = await judged("loose-vertex.blend", { size: { x: [0.99, 1.01], y: [0.99, 1.01], z: [0.79, 0.81] }, origin: "bottom-centre", manifold: true }, "loose");
    expect(report.measurements?.size).toEqual([1, 1, 0.8]);
    expect(report.measurements?.bounds).toEqual({ min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] });
    expect(report.measurements?.manifold).toMatchObject({ looseVertices: 1, wireEdges: 1 });
    expect(failing(report)).toEqual(["manifold"]);
  });
});

describe("measurement fixes", { timeout: 180_000 }, () => {
  it("measures four wheels sharing one mesh once for UV and topology, and every one for triangles", async () => {
    const report = await judged("instanced.glb", { uv: { required: true, maxOverlap: 0 }, triangles: { min: 252, max: 252 } }, "wheels");
    expect(failing(report)).toEqual([]);
    expect(report.measurements?.triangles).toBe(12 + 4 * 60);
    expect(report.measurements?.objects).toBe(5);
    expect(report.measurements?.uv.overlap).toBe(0);
    expect(report.measurements?.shells.count).toBe(5);
    expect(report.measurements?.manifold.looseParts).toBe(2);
  });

  it("gives the same bounds for an animated crate saved on frame 1 and on frame 40", async () => {
    const first = await judged("animated-1.blend", {}, "frame");
    const fortieth = await judged("animated-40.blend", {}, "frame");
    expect(first.measurements?.bounds).toEqual({ min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] });
    expect(fortieth.measurements?.bounds).toEqual(first.measurements?.bounds);
    expect(fortieth.measurements?.origin).toEqual(first.measurements?.origin);
  });

  it("measures a .blend in centimetres in metres: 100 x 100 x 80 units at scale 0.01 is 1 x 1 x 0.8 m, its origin 0.5 m along x", async () => {
    const report = await judged("centimetres.blend", { size: { x: [0.99, 1.01], y: [0.99, 1.01], z: [0.79, 0.81] } }, "units");
    expect(failing(report)).toEqual([]);
    expect(report.measurements?.size).toEqual([1, 1, 0.8]);
    expect(report.measurements?.origin.point).toEqual([0.5, 0, 0]);
    expect(report.measurements?.unitScale).toBeCloseTo(0.01, 6);
  });

  it("wraps UVs outside 0-1: six faces each one tile further along u land on the same spot and overlap", async () => {
    const report = await judged("wrapped-uv.glb", { uv: { required: true, maxOverlap: 0.05 } }, "wrapped");
    expect(report.measurements?.uv).toEqual({ present: true, meshesWithoutUv: 0, coverage: 0.0625, overlap: 1, outsideUnitSquare: 0.807692 });
    expect(failing(report)).toEqual(["uv.maxOverlap"]);
  });
});

describe("per-object rules", { timeout: 180_000 }, () => {
  it("checks objects matched by a name pattern: the four 0.3 m wheels, the body pivot, and a missing spoiler", async () => {
    const named = [
      { name: "Wheel.*", required: true, triangles: { max: 60 }, size: { x: [0.29, 0.31], z: [0.29, 0.31], maxExtent: 0.31 }, origin: "centre", materials: { max: 1 } },
      { name: "Body", origin: { point: [0, 0, 0], tolerance: 0.001 } },
      { name: "Spoiler*", required: true },
      { name: "Wheel.00?", triangles: { max: 59 } },
    ];
    const report = await judged("instanced.glb", { objects: { max: 5, named } }, "named");
    expect(failing(report)).toEqual(["objects[Spoiler*].required", "objects[Wheel.00?].triangles.max"]);
    expect(report.rules.find((rule) => rule.rule === "objects[Wheel.*].required")?.measured).toEqual({ objects: 4, names: ["Wheel.000", "Wheel.001", "Wheel.002", "Wheel.003"] });
    expect(report.rules.find((rule) => rule.rule === "objects[Wheel.00?].triangles.max")?.measured).toEqual({
      objects: 4,
      failing: ["Wheel.000: 60", "Wheel.001: 60", "Wheel.002: 60", "Wheel.003: 60"],
    });
    const body = report.measurements?.objectList?.items.find((item) => item.name === "Body");
    expect(body).toMatchObject({ triangles: 12, size: [1.2, 0.6, 0.3], origin: { point: [0, 0, 0] } });
  });
});
