import { describe, expect, it } from "vitest";
import { planPass } from "../../src/judge/judge-pass.js";
import type { Measurements } from "../../src/judge/measurements.js";
import type { NaturalMeasurements } from "../../src/judge/natural-schema.js";
import { calibratedLimits, NATURAL_CLASSES } from "../../src/judge/natural-spec.js";
import { naturalLines, naturalRules, RENDERED_RULES } from "../../src/judge/natural.js";
import { evaluateRules } from "../../src/judge/rules.js";
import { parseSpec, SpecError } from "../../src/judge/spec.js";
import { CRATE_MEASUREMENTS } from "./measured.js";

function problems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

const MEASURED: NaturalMeasurements = {
  repetition: { minShift: 16, minOverlap: 0.25, window: 33, minEnergy: 0.1, worst: 0.42, view: "front", shift: [20, 3], views: { front: { peak: 0.42, shift: [20, 3], size: [480, 480] } }, failure: null },
  instanceRepetition: { objects: "*", scaleTolerance: 0.01, yawToleranceDegrees: 5, pieces: 200, meshes: 3, share: 0.03, largestGroup: 6, group: { mesh: "rock", scale: 1.2, yaw: 30 }, failure: null },
  leonardo: { median: 2.1, p25: 1.9, p75: 2.2, branchings: 40, measured: 38, solved: 38, above: 0, unmeasured: 2, ceiling: 10, skeletons: [], deltas: [], refused: [], failure: null },
  sizeDistribution: { by: "sphere", objects: "*", count: 300, unmeasured: 0, exponent: -2.05, xMin: 0.1, xMax: 1, tail: 250, ks: 0.03, failure: null },
};

function measured(natural: NaturalMeasurements | undefined): Measurements {
  return { ...CRATE_MEASUREMENTS, ...(natural === undefined ? {} : { natural }) };
}

function judged(natural: Record<string, unknown>, values: NaturalMeasurements | undefined) {
  const spec = parseSpec({ format: "glb", natural });
  return [...evaluateRules(spec, measured(values)), ...naturalRules(spec.natural, values, RENDERED_RULES)].filter((rule) => rule.rule.startsWith("natural."));
}

describe("the natural rules of part two in an asset spec", () => {
  it("take Leonardo's default from Eloy for trees and the instance repetition default from the research, and say so", () => {
    const [leonardo] = judged({ class: "tree", leonardo: {} }, MEASURED);
    expect(leonardo).toMatchObject({ rule: "natural.leonardo", pass: true, limit: { min: 1.8, max: 2.3, class: "tree", source: "cited", cites: expect.stringContaining("S53") } });
    for (const kind of NATURAL_CLASSES) {
      const [instances] = judged({ class: kind, instanceRepetition: {} }, MEASURED);
      expect(instances).toMatchObject({ pass: true, limit: { max: 0.1, source: "cited", cites: expect.stringContaining("not verified") } });
    }
  });

  it("refuse an empty Leonardo rule for classes Eloy's range does not cover", () => {
    for (const kind of ["rock", "plant"]) expect(problems({ format: "glb", natural: { class: kind, leonardo: {} } }).join(" ")).toMatch(/natural\.leonardo: leonardo has no calibrated default/);
    expect(problems({ format: "glb", natural: { class: "rock", leonardo: { min: 1.5, max: 3 } } })).toEqual([]);
  });

  it("keep a name pattern beside the default limits, and the size measure beside given limits", () => {
    const [instances] = judged({ class: "rock", instanceRepetition: { objects: "rubble_*" } }, MEASURED);
    expect(instances?.limit).toMatchObject({ max: 0.1, objects: "rubble_*", source: "cited" });
    const [sizes] = judged({ class: "rock", sizeDistribution: { min: -2.5, max: -1.5, by: "sphere", objects: "rubble_*" } }, MEASURED);
    expect(sizes).toMatchObject({ pass: true, limit: { min: -2.5, max: -1.5, by: "sphere", objects: "rubble_*", source: "spec" } });
  });

  it("refuse crossed or out-of-range limits and unknown size measures", () => {
    expect(problems({ format: "glb", natural: { class: "tree", leonardo: { min: 2.3, max: 1.8 } } }).join(" ")).toMatch(/min must not exceed max/);
    expect(problems({ format: "glb", natural: { class: "rock", repetition: { max: 1.5 } } })).not.toEqual([]);
    expect(problems({ format: "glb", natural: { class: "rock", sizeDistribution: { min: -2.5, by: "height" } } })).not.toEqual([]);
    expect(problems({ format: "glb", natural: { class: "rock", instanceRepetition: { max: 0.1, share: 0.1 } } })).not.toEqual([]);
  });

  it("need limits for repetition and size distribution where the calibration gives no default", () => {
    for (const kind of NATURAL_CLASSES) {
      for (const rule of ["repetition", "sizeDistribution"] as const) {
        const found = problems({ format: "glb", natural: { class: kind, [rule]: {} } });
        expect(found.length === 0, `${kind} ${rule}`).toBe(calibratedLimits(kind, rule) !== undefined);
      }
    }
  });

  it("check each limit against the measured value", () => {
    expect(judged({ class: "rock", repetition: { max: 0.4 } }, MEASURED)[0]).toMatchObject({ pass: false, measured: { worst: 0.42, view: "front", shift: [20, 3] } });
    expect(judged({ class: "rock", instanceRepetition: { max: 0.02 } }, MEASURED)[0]?.pass).toBe(false);
    expect(judged({ class: "tree", leonardo: { min: 2.2 } }, MEASURED)[0]?.pass).toBe(false);
    expect(judged({ class: "rock", sizeDistribution: { min: -2, max: -1.5 } }, MEASURED)[0]?.pass).toBe(false);
  });

  it("fail every rule with a null value when nothing was measured", () => {
    const results = judged({ class: "tree", repetition: { max: 1 }, instanceRepetition: { max: 1 }, leonardo: { min: 0, max: 10 }, sizeDistribution: { min: -12, max: 8 } }, undefined);
    expect(results.map((result) => [result.rule, result.pass])).toEqual([
      ["natural.instanceRepetition", false],
      ["natural.leonardo", false],
      ["natural.sizeDistribution", false],
      ["natural.repetition", false],
    ]);
    for (const result of results) expect(Object.values(result.measured as Record<string, unknown>)).toContain(null);
  });

  it("leave repetition to the views: the measured rules never include it", () => {
    const spec = parseSpec({ format: "glb", natural: { class: "rock", repetition: { max: 0.8 } } });
    expect(evaluateRules(spec, measured(MEASURED)).filter((rule) => rule.rule.startsWith("natural."))).toEqual([]);
  });

  it("print their values on the natural line of the summary", () => {
    expect(naturalLines(MEASURED)).toEqual([
      "  natural: repetition worst 0.42 in front at shift 20,3; instance repetition 0.03 (6 of 200 pieces alike); Leonardo median delta 2.1 over 38 branchings; size exponent -2.05 above 0.1 m over 250 of 300 sphere sizes",
    ]);
  });
});

describe("the one judge pass with the natural rules of part two", () => {
  const delivery = { folder: "/delivery", main: "/delivery/tree.glb", files: [], bytes: 1, sha256: "0".repeat(64), references: { files: 0, unresolved: [] } };
  const plan = (natural: Record<string, unknown>) => planPass({ spec: parseSpec({ format: "glb", natural }), delivery, references: null, maxTriangles: 1000, timeoutMs: 1000, mode: "cpu", render: {}, visual: {} });

  it("measures instances, sizes and skeletons in the measure stage, with their patterns", () => {
    const tree = plan({ class: "tree", instanceRepetition: { objects: "Leaf*" }, leonardo: {}, sizeDistribution: { min: -2.5, max: -1.5 } });
    expect(tree.stages).toEqual(["measure", "views", "sheet"]);
    const args = tree.args.join(" ");
    expect(args).toContain("--natural instances,sizes,leonardo --natural-instances Leaf* --natural-sizes trunk:*");
    expect(plan({ class: "rock", sizeDistribution: { min: -2.5, objects: "rubble_*" } }).args.join(" ")).toContain("--natural sizes --natural-sizes sphere:rubble_*");
  });

  it("adds no stage and no argument for repetition, which reads the views", () => {
    const repetition = plan({ class: "rock", repetition: { max: 0.8 } });
    expect(repetition.stages).toEqual(["measure", "views", "sheet"]);
    expect(repetition.args.join(" ")).not.toContain("--natural");
  });
});
