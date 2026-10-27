import { describe, expect, it } from "vitest";
import { renderRules } from "../../src/judge/integrity-rules.js";
import type { Measurements } from "../../src/judge/measurements.js";
import { globPattern } from "../../src/judge/object-rules.js";
import { evaluateRules } from "../../src/judge/rules.js";
import { toBlender } from "../../src/judge/shape-rules.js";
import { parseSpec, SpecError } from "../../src/judge/spec.js";
import { CRATE_MEASUREMENTS } from "./measured.js";

function failing(rules: Record<string, unknown>, measurements: Measurements = CRATE_MEASUREMENTS): string[] {
  return evaluateRules(parseSpec({ format: "glb", ...rules }), measurements)
    .filter((rule) => !rule.pass)
    .map((rule) => rule.rule);
}

function problems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

describe("axes", () => {
  it("maps glTF axes to Blender axes when upAxis is y: the crate's 0.8 m height is glTF y", () => {
    const gltf = { x: [0.95, 1.05], y: [0.75, 0.85], z: [0.95, 1.05] };
    expect(failing({ upAxis: "y", size: gltf })).toEqual([]);
    expect(failing({ size: gltf })).toEqual(["size.y", "size.z"]);
    expect(toBlender([1, 2, 3], "y")).toEqual([1, -3, 2]);
    expect(toBlender([1, 2, 3], "z")).toEqual([1, 2, 3]);
  });

  it("checks an origin given as a point, in the spec's axes", () => {
    expect(failing({ origin: { point: [0, 0, 0], tolerance: 0.001 } })).toEqual([]);
    const off = evaluateRules(parseSpec({ format: "glb", origin: { point: [0, 0, 0.4], tolerance: 0.01 } }), CRATE_MEASUREMENTS)[1];
    expect(off).toEqual({ rule: "origin", measured: { at: [0, 0, 0], source: "object Crate", distanceFromRequired: 0.4 }, limit: { at: [0, 0, 0.4], tolerance: 0.01 }, pass: false });
    expect(failing({ upAxis: "y", origin: { point: [0, 0.4, 0], tolerance: 0.01 } }, { ...CRATE_MEASUREMENTS, origin: { ...CRATE_MEASUREMENTS.origin, point: [0, 0, 0.4] } })).toEqual([]);
  });

  it("bounds the longest side with minExtent and maxExtent", () => {
    expect(failing({ size: { minExtent: 1, maxExtent: 1 } })).toEqual([]);
    expect(failing({ size: { minExtent: 1.01 } })).toEqual(["size.minExtent"]);
    expect(failing({ size: { maxExtent: 0.99 } })).toEqual(["size.maxExtent"]);
    expect(problems({ format: "glb", size: { minExtent: 2, maxExtent: 1 } })).toEqual(["size: minExtent must not exceed maxExtent"]);
  });
});

describe("rules that resist gaming", () => {
  const gamed: Measurements = {
    ...CRATE_MEASUREMENTS,
    triangles: 252,
    visibleTriangles: 12,
    shells: { count: 5, closed: 5, inverted: 1 },
    faces: { degenerate: 2, duplicate: 3, hiddenRatio: 0.2, hiddenFaces: 240, tested: 252, sampled: false },
  };

  it("fails each rule on its own measurement, at its limit inclusive", () => {
    expect(failing({ triangles: { minVisible: 12 }, faces: { maxDegenerate: 2, maxDuplicate: 3, maxHiddenRatio: 0.2 }, shells: { max: 5 } }, gamed)).toEqual([]);
    expect(failing({ triangles: { minVisible: 13 } }, gamed)).toEqual(["triangles.minVisible"]);
    expect(failing({ faces: { maxDegenerate: 1 } }, gamed)).toEqual(["faces.maxDegenerate"]);
    expect(failing({ faces: { maxDuplicate: 2 } }, gamed)).toEqual(["faces.maxDuplicate"]);
    expect(failing({ faces: { maxHiddenRatio: 0.19 } }, gamed)).toEqual(["faces.maxHiddenRatio"]);
    expect(failing({ shells: { max: 4 } }, gamed)).toEqual(["shells.max"]);
    expect(failing({ manifold: { noInverted: true } }, gamed)).toEqual(["manifold.noInverted"]);
  });

  it("keeps manifold: true as before, and adds the inverted check only on request", () => {
    expect(failing({ manifold: true }, gamed)).toEqual([]);
    expect(failing({ manifold: { required: true } }, gamed)).toEqual([]);
    const rules = evaluateRules(parseSpec({ format: "glb", manifold: { required: true, noInverted: true } }), gamed).map((rule) => rule.rule);
    expect(rules).toEqual(["format", "manifold", "manifold.noInverted"]);
  });

  it("fails selfContained for unresolved and refused references", () => {
    expect(failing({ selfContained: true })).toEqual([]);
    const unresolved = { ...CRATE_MEASUREMENTS, references: { files: 1, unresolved: ["texture wood.png: the file is not in the asset folder"] } };
    expect(failing({ selfContained: true }, unresolved)).toEqual(["selfContained"]);
    expect(failing({ selfContained: true }, { ...CRATE_MEASUREMENTS, externalFilesRefused: ["images:wood"] })).toEqual(["selfContained"]);
    expect(failing({}, unresolved)).toEqual([]);
  });

  it("passes renders.required only for rendered views", () => {
    const spec = parseSpec({ format: "glb", renders: { required: true } });
    expect(renderRules(spec, { status: "rendered", reason: null })[0]?.pass).toBe(true);
    for (const status of ["preview", "skipped", "failed"] as const) expect(renderRules(spec, { status, reason: "why" })[0]?.pass).toBe(false);
    expect(renderRules(spec, null)[0]?.pass).toBe(false);
    expect(renderRules(parseSpec({ format: "glb" }), null)).toEqual([]);
  });
});

describe("per-object rules", () => {
  it("matches names with * and ? only, and nothing else as a pattern", () => {
    expect(globPattern("Wheel.*").test("Wheel.001")).toBe(true);
    expect(globPattern("Wheel.*").test("WheelX001")).toBe(false);
    expect(globPattern("Bolt?").test("Bolt7")).toBe(true);
    expect(globPattern("Bolt?").test("Bolt12")).toBe(false);
    expect(globPattern("a+b(c)").test("a+b(c)")).toBe(true);
  });

  it("fails a named rule without the per-object list, and refuses repeated patterns", () => {
    expect(failing({ objects: { named: [{ name: "Body", required: true }] } })).toEqual(["objects[Body].measured"]);
    expect(problems({ format: "glb", objects: { named: [{ name: "A" }, { name: "A" }] } })).toEqual(["objects: named object patterns must not repeat"]);
  });
});
