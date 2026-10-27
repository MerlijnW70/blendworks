import { describe, expect, it } from "vitest";
import type { Measurements } from "../../src/judge/measurements.js";
import { summarize } from "../../src/judge/report.js";
import { evaluateRules, originTolerance } from "../../src/judge/rules.js";
import { parseSpec } from "../../src/judge/spec.js";
import { CRATE_SPEC } from "./helpers.js";
import { assetRecord, CRATE_MEASUREMENTS } from "./measured.js";

const CRATE: Measurements = CRATE_MEASUREMENTS;

const spec = parseSpec(CRATE_SPEC);

function failing(measurements: Measurements, overrides: Record<string, unknown> = {}): string[] {
  return evaluateRules(parseSpec({ ...CRATE_SPEC, ...overrides }), measurements)
    .filter((rule) => !rule.pass)
    .map((rule) => rule.rule);
}

describe("the rules", () => {
  it("checks every rule of the example spec, with its measured value and limit", () => {
    const rules = evaluateRules(spec, CRATE);
    expect(rules.map((rule) => rule.rule)).toEqual([
      "format",
      "triangles.max",
      "size.x",
      "size.y",
      "size.z",
      "origin",
      "manifold",
      "materials.min",
      "materials.max",
      "uv.required",
      "uv.maxOverlap",
      "objects.max",
      "fileSize.maxBytes",
    ]);
    expect(rules.every((rule) => rule.pass)).toBe(true);
    expect(rules.find((rule) => rule.rule === "size.z")).toEqual({ rule: "size.z", measured: 0.8, limit: [0.75, 0.85], pass: true });
  });

  it("checks only format when the spec has nothing else", () => {
    expect(evaluateRules(parseSpec({ format: "glb" }), CRATE)).toEqual([{ rule: "format", measured: "glb", limit: "glb", pass: true }]);
  });

  it("includes both ends of every range", () => {
    expect(failing({ ...CRATE, triangles: 800, size: [0.95, 1.05, 0.85], materials: { count: 3, names: [] } })).toEqual([]);
    expect(failing({ ...CRATE, triangles: 801 })).toEqual(["triangles.max"]);
    expect(failing({ ...CRATE, size: [0.949999, 1, 0.8] })).toEqual(["size.x"]);
    expect(failing({ ...CRATE, materials: { count: 0, names: [] } })).toEqual(["materials.min"]);
    expect(failing({ ...CRATE, fileBytes: 2_000_001 })).toEqual(["fileSize.maxBytes"]);
    expect(failing({ ...CRATE, objects: 2 })).toEqual(["objects.max"]);
  });

  it("allows the origin 1% of the largest side, at least 1 mm, off the required point", () => {
    expect(originTolerance([1, 1, 0.8])).toBe(0.01);
    expect(originTolerance([0.01, 0.01, 0.01])).toBe(0.001);
    const near = { ...CRATE.origin, bottomCentreDistance: 0.01, centreDistance: 0.39 };
    expect(failing({ ...CRATE, origin: near })).toEqual([]);
    expect(failing({ ...CRATE, origin: { ...near, bottomCentreDistance: 0.0101 } })).toEqual(["origin"]);
    expect(failing({ ...CRATE, origin: { ...CRATE.origin, bottomCentreDistance: 0.4, centreDistance: 0 } }, { origin: "centre" })).toEqual([]);
  });

  it("counts every topology defect against manifold, but not separate parts", () => {
    for (const defect of ["nonManifoldEdges", "boundaryEdges", "wireEdges", "nonManifoldVertices", "looseVertices"]) {
      expect(failing({ ...CRATE, manifold: { ...CRATE.manifold, [defect]: 1 } }), defect).toEqual(["manifold"]);
    }
    expect(failing({ ...CRATE, manifold: { ...CRATE.manifold, looseParts: 9 } })).toEqual([]);
    expect(failing({ ...CRATE, manifold: { ...CRATE.manifold, boundaryEdges: 4 } }, { manifold: false })).toEqual([]);
  });

  it("fails UV overlap and coverage limits when there are no UVs to measure", () => {
    const bare = { ...CRATE, uv: { present: false, meshesWithoutUv: 1, coverage: 0, overlap: 0, outsideUnitSquare: 0 } };
    expect(failing(bare, { uv: { maxOverlap: 0.05, minCoverage: 0.2 } })).toEqual(["uv.maxOverlap", "uv.minCoverage"]);
    expect(failing(CRATE, { uv: { minCoverage: 0.5 } })).toEqual(["uv.minCoverage"]);
    expect(failing({ ...CRATE, uv: { ...CRATE.uv, overlap: 0.0501 } })).toEqual(["uv.maxOverlap"]);
  });

  it("summarises each rule in one line", () => {
    const rules = evaluateRules(spec, { ...CRATE, triangles: 900 });
    const text = summarize({
      passed: false,
      preview: false,
      spec: { path: "spec.json", sha256: null, name: "wooden crate" },
      asset: assetRecord("crate.glb", 2784),
      blender: "5.2.3",
      sandbox: null,
      renderSandbox: null,
      device: null,
      failure: null,
      rules,
      measurements: CRATE,
      renders: null,
      timings: { measure: null, device: null, render: null, sheet: null, total: 0 },
    });
    expect(text.split("\n")[0]).toBe("FAIL  wooden crate  (crate.glb)");
    expect(text).toContain("FAIL  triangles.max      measured 900; required at most 800");
    expect(text).toContain("12 of 13 rules pass");
  });
});
