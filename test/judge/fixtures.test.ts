import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";

let assets = "";
let markers = "";
let specs = "";

beforeAll(() => {
  ({ assets, markers } = makeFixtures("fixtures"));
  specs = freshDir("fixtures", "specs");
}, 180_000);

async function judged(asset: string, specOverrides: Record<string, unknown> = {}): Promise<Report> {
  const name = asset.replace(/\W+/g, "-");
  const spec = writeSpec(specs, name, specOverrides);
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: join(freshDir("fixtures", "reports", name)) });
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

function expectRendered(report: Report, views: number): void {
  expect(report.renders).not.toBeNull();
  expect(report.renders?.views).toHaveLength(views);
  for (const view of report.renders?.views ?? []) expect(statSync(view.path).size).toBeGreaterThan(1000);
  const sheet = report.renders?.contactSheet ?? "";
  expect(statSync(sheet).size).toBeGreaterThan(10_000);
  expect(readFileSync(sheet).subarray(1, 4).toString("latin1")).toBe("PNG");
}

const CRATE_SIZE = [1, 1, 0.8];
const SOUND = { nonManifoldEdges: 0, boundaryEdges: 0, wireEdges: 0, nonManifoldVertices: 0, looseVertices: 0, looseParts: 1 };

describe("judging the fixture assets", { timeout: 120_000 }, () => {
  it("passes the 1 x 1 x 0.8 crate: 6 quads make 12 triangles, the cross UV layout covers 6 x 0.25 x 0.25 = 0.375", async () => {
    const report = await judged("crate.glb");
    expect(failing(report)).toEqual([]);
    expect(report.passed).toBe(true);
    const measurements = report.measurements!;
    expect(measurements.triangles).toBe(12);
    expect(measurements.objects).toBe(1);
    expect(measurements.size).toEqual(CRATE_SIZE);
    expect(measurements.bounds).toEqual({ min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] });
    expect(measurements.origin.point).toEqual([0, 0, 0]);
    expect(measurements.origin.bottomCentreDistance).toBe(0);
    expect(measurements.origin.centreDistance).toBe(0.4);
    expect(measurements.manifold).toEqual(SOUND);
    expect(measurements.materials).toEqual({ count: 2, names: ["metal", "wood"] });
    expect(measurements.uv).toEqual({ present: true, meshesWithoutUv: 0, coverage: 0.375, overlap: 0 });
    expect(measurements.fileBytes).toBe(statSync(join(assets, "crate.glb")).size);
    expectRendered(report, 6);
  });

  it("fails the crate made of 192 triangles by an unapplied modifier: 6 faces x 4^2 quads x 2", async () => {
    const report = await judged("over-budget.blend", { format: "blend", triangles: { max: 100 } });
    expect(report.measurements?.triangles).toBe(192);
    expect(failing(report)).toEqual(["triangles.max"]);
    expect(report.passed).toBe(false);
    expectRendered(report, 6);
  });

  it("fails the 2 m wide crate on size.x only", async () => {
    const report = await judged("wrong-size.glb");
    expect(report.measurements?.size).toEqual([2, 1, 0.8]);
    expect(failing(report)).toEqual(["size.x"]);
    expectRendered(report, 6);
  });

  it("fails the crate whose origin is its centre, 0.4 m above the bottom centre", async () => {
    const report = await judged("centre-origin.glb");
    expect(report.measurements?.bounds).toEqual({ min: [-0.5, -0.5, -0.4], max: [0.5, 0.5, 0.4] });
    expect(report.measurements?.origin.bottomCentreDistance).toBe(0.4);
    expect(report.measurements?.origin.centreDistance).toBe(0);
    expect(failing(report)).toEqual(["origin"]);
    expect(report.rules.find((rule) => rule.rule === "origin")?.measured).toMatchObject({ at: "centre" });
    expectRendered(report, 6);
  });

  it("fails the box without a lid: 10 triangles and the 4 rim edges open", async () => {
    const report = await judged("open-box.glb");
    expect(report.measurements?.triangles).toBe(10);
    expect(report.measurements?.manifold).toEqual({ ...SOUND, boundaryEdges: 4 });
    expect(report.measurements?.uv.coverage).toBe(0.3125);
    expect(failing(report)).toEqual(["manifold"]);
    expectRendered(report, 6);
  });

  it("fails the crate without UVs on uv.required and uv.maxOverlap", async () => {
    const report = await judged("no-uv.glb");
    expect(report.measurements?.uv).toEqual({ present: false, meshesWithoutUv: 1, coverage: 0, overlap: 0 });
    expect(failing(report)).toEqual(["uv.required", "uv.maxOverlap"]);
    expectRendered(report, 6);
  });

  it("fails the crate whose 6 faces all fill the whole UV square: coverage 1, overlap 1", async () => {
    const report = await judged("overlap-uv.glb");
    expect(report.measurements?.uv).toEqual({ present: true, meshesWithoutUv: 0, coverage: 1, overlap: 1 });
    expect(failing(report)).toEqual(["uv.maxOverlap"]);
    expectRendered(report, 6);
  });

  it("measures the same crate from .gltf, .fbx, .obj and .blend", async () => {
    for (const [asset, format] of [["crate.gltf", "gltf"], ["crate.fbx", "fbx"], ["crate.obj", "obj"], ["crate.blend", "blend"]] as const) {
      const report = await judged(asset, { format, views: ["three-quarter"] });
      expect(failing(report), asset).toEqual([]);
      expect(report.measurements?.triangles, asset).toBe(12);
      expect(report.measurements?.size, asset).toEqual(CRATE_SIZE);
      expect(report.measurements?.materials.count, asset).toBe(2);
      expectRendered(report, 1);
    }
  });

  it("fails the format rule when the delivery is not the format the spec asks for", async () => {
    const report = await judged("crate.fbx", { views: ["front"] });
    expect(failing(report)).toEqual(["format"]);
  });
});

describe("a .blend with auto-run code", { timeout: 120_000 }, () => {
  const markerNames = () => readdirSync(markers).filter((name) => name.endsWith(".marker")).sort();

  it("runs its code when Blender opens it with auto-run on, so the fixture is armed", () => {
    rmSync(markers, { recursive: true, force: true });
    freshDir("fixtures", "markers");
    execFileSync(
      blenderPath(),
      ["--background", "--enable-autoexec", join(assets, "autorun.blend"), "--python-expr", "import bpy; bpy.context.view_layer.update()"],
      { stdio: "pipe", timeout: 60_000 },
    );
    expect(markerNames()).toEqual(["autorun-driver.marker", "autorun-text.marker"]);
  });

  it("never runs it in the judge, which still measures the crate", async () => {
    rmSync(markers, { recursive: true, force: true });
    freshDir("fixtures", "markers");
    const report = await judged("autorun.blend", { format: "blend" });
    expect(markerNames()).toEqual([]);
    expect(existsSync(join(markers, "autorun-text.marker"))).toBe(false);
    expect(report.measurements?.triangles).toBe(12);
    expect(report.measurements?.origin.point).toEqual([0, 0, 0]);
    expect(failing(report)).toEqual([]);
    expectRendered(report, 6);
  });
});
