import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { CRATE_MEASUREMENTS } from "./measured.js";
import { useBlenderSlot } from "../setup/slot.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(() => {
  ({ assets } = makeFixtures("old-specs"));
  specs = freshDir("old-specs", "specs");
}, 180_000);

const REPORT_KEYS = ["passed", "preview", "spec", "asset", "blender", "sandbox", "renderSandbox", "device", "failure", "rules", "measurements", "renders", "timings", "summary"];

const MEASUREMENTS = CRATE_MEASUREMENTS;

const SUMMARY = [
  "PASS  wooden crate  (ASSET)",
  "  pass  format             measured glb; required glb",
  "  pass  triangles.max      measured 12; required at most 800",
  "  pass  size.x             measured 1; required between [0.95, 1.05]",
  "  pass  size.y             measured 1; required between [0.95, 1.05]",
  "  pass  size.z             measured 0.8; required between [0.75, 0.85]",
  "  pass  origin             measured bottom-centre, 0 m from the required point; required bottom-centre within 0.01 m",
  "  pass  manifold           measured nonManifoldEdges 0, boundaryEdges 0, wireEdges 0, nonManifoldVertices 0, looseVertices 0, looseParts 1; required nonManifoldEdges 0, boundaryEdges 0, wireEdges 0, nonManifoldVertices 0, looseVertices 0",
  "  pass  materials.min      measured 2; required at least 1",
  "  pass  materials.max      measured 2; required at most 3",
  "  pass  uv.required        measured true; required true",
  "  pass  uv.maxOverlap      measured 0; required at most 0.05",
  "  pass  objects.max        measured 1; required at most 1",
  "  pass  fileSize.maxBytes  measured 2784; required at most 2000000",
  "  13 of 13 rules pass",
  "  surface: 12 of 12 triangles visible from outside, hidden ratio 0; 0 degenerate, 0 duplicate faces; 1 shells, 1 closed, 0 inside out",
  "  views: skipped (preview); the rules alone decide pass or fail",
  "  contact sheet: SHEET",
  "  delivery: 1 files, 2784 bytes, set sha256 SET",
  "  sandbox: SANDBOX",
  "  time: TIME",
];

describe("a spec without the new rules", { timeout: 120_000 }, () => {
  it("gives the rules, verdict and summary it gave before, with the new measurements beside them", async () => {
    const outDir = freshDir("old-specs", "report");
    const report = await judge({ specPath: writeSpec(specs, "crate"), assetPath: join(assets, "crate.glb"), outDir, preview: true });
    const written = JSON.parse(readFileSync(join(outDir, "report.json"), "utf8"));
    expect(Object.keys(written)).toEqual(REPORT_KEYS);
    expect(Object.keys(written.measurements)).toEqual(Object.keys(MEASUREMENTS));
    expect(written.measurements).toEqual(MEASUREMENTS);
    expect(Object.keys(written.timings)).toEqual(["measure", "device", "render", "sheet", "total"]);
    expect(written.rules.map((rule: { rule: string; pass: boolean }) => [rule.rule, rule.pass])).toEqual(
      ["format", "triangles.max", "size.x", "size.y", "size.z", "origin", "manifold", "materials.min", "materials.max", "uv.required", "uv.maxOverlap", "objects.max", "fileSize.maxBytes"].map((rule) => [rule, true]),
    );
    const summary = report.summary
      .split(report.asset.path)
      .join("ASSET")
      .split(report.renders!.contactSheet!)
      .join("SHEET")
      .replace(/set sha256 [0-9a-f]{64}/, "set sha256 SET")
      .replace(/sandbox: .*/, "sandbox: SANDBOX")
      .replace(/time: .*/, "time: TIME");
    expect(summary.split("\n")).toEqual(SUMMARY);
    expect(existsSync(join(outDir, "validation.json"))).toBe(true);
    const measured = JSON.parse(readFileSync(join(outDir, "measurements.json"), "utf8")).measurements;
    expect(measured.textures).toMatchObject({ count: 0, gpuBytes: 0 });
    expect(measured.floating).toBeUndefined();
  });
});
