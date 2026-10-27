import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { planPass } from "../../src/judge/judge-pass.js";
import type { Measurements } from "../../src/judge/measurements.js";
import { NATURAL_DEFAULTS } from "../../src/judge/natural-defaults.js";
import type { NaturalMeasurements } from "../../src/judge/natural-schema.js";
import { calibratedLimits, NATURAL_CLASSES, NATURAL_RULES } from "../../src/judge/natural-spec.js";
import { naturalLines } from "../../src/judge/natural.js";
import { stageDigest } from "../../src/judge/onepass.js";
import { evaluateRules } from "../../src/judge/rules.js";
import { parseSpec, SpecError, specJsonSchema } from "../../src/judge/spec.js";
import { freshDir } from "./helpers.js";
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

const ROCK_LIKE: NaturalMeasurements = {
  silhouettes: {
    size: 1024,
    views: {},
    dimension: 0.98,
    solidity: 0.9,
    failure: null,
  },
  surfaceRoughness: { samplesPerObject: 4096, radiusDivisor: 32, flatDegrees: 3, objects: 2, lowestP90: 30, highestFlatShare: 0.05, items: [] },
  albedoVariation: { cv: 0.3, texels: 1000, mean: 0.4, images: [], untexturedShare: 0 },
};

function judged(natural: Record<string, unknown>, measured: NaturalMeasurements | undefined) {
  const measurements: Measurements = { ...CRATE_MEASUREMENTS, ...(measured === undefined ? {} : { natural: measured }) };
  return evaluateRules(parseSpec({ format: "glb", natural }), measurements).filter((rule) => rule.rule.startsWith("natural."));
}

describe("the natural group of an asset spec", () => {
  it("needs a class and at least one rule", () => {
    expect(problems({ format: "glb", natural: { solidity: { max: 0.9 } } })[0]).toMatch(/^natural\.class/);
    expect(problems({ format: "glb", natural: { class: "rock" } }).join(" ")).toMatch(/needs at least one of silhouetteDimension, solidity, surfaceRoughness, albedoVariation/);
    expect(problems({ format: "glb", natural: { class: "rock", solidity: { max: 0.9 } } })).toEqual([]);
  });

  it("refuses an empty rule that has no calibrated default for the class, and accepts it with limits", () => {
    for (const kind of NATURAL_CLASSES) {
      for (const rule of NATURAL_RULES) {
        const found = problems({ format: "glb", natural: { class: kind, [rule]: {} } });
        if (calibratedLimits(kind, rule) === undefined) expect(found.join(" ")).toMatch(new RegExp(`natural\\.${rule}: ${rule} has no calibrated default for class ${kind}`));
        else expect(found).toEqual([]);
      }
    }
    expect(problems({ format: "glb", natural: { class: "tree", albedoVariation: { min: 0.1 } } })).toEqual([]);
  });

  it("refuses limits out of range or crossed", () => {
    expect(problems({ format: "glb", natural: { class: "rock", solidity: { min: 0.9, max: 0.5 } } }).join(" ")).toMatch(/min must not exceed max/);
    expect(problems({ format: "glb", natural: { class: "rock", solidity: { max: 1.5 } } })).not.toEqual([]);
    expect(problems({ format: "glb", natural: { class: "rock", surfaceRoughness: { p90Min: 15, flat: 0.2 } } })).not.toEqual([]);
  });

  it("is in the published JSON schema", () => {
    expect(JSON.stringify(specJsonSchema())).toContain("surfaceRoughness");
  });
});

describe("natural rules", () => {
  it("apply the calibrated defaults of the class to an empty rule, and say so", () => {
    for (const [kind, rules] of Object.entries(NATURAL_DEFAULTS)) {
      for (const [rule, limits] of Object.entries(rules)) {
        const [result] = judged({ class: kind, [rule]: {} }, ROCK_LIKE);
        expect(result?.limit).toEqual({ ...limits, class: kind, source: "calibrated" });
      }
    }
  });

  it("apply only the limits a rule gives", () => {
    const [low] = judged({ class: "rock", solidity: { min: 0.95 } }, ROCK_LIKE);
    expect(low).toEqual({ rule: "natural.solidity", measured: { lowest: 0.9, views: { front: null, right: null, top: null } }, limit: { min: 0.95, class: "rock", source: "spec" }, pass: false });
    const [high] = judged({ class: "rock", solidity: { max: 0.95 } }, ROCK_LIKE);
    expect(high?.pass).toBe(true);
  });

  it("check both roughness limits", () => {
    expect(judged({ class: "rock", surfaceRoughness: { p90Min: 25, flatShareMax: 0.1 } }, ROCK_LIKE)[0]?.pass).toBe(true);
    expect(judged({ class: "rock", surfaceRoughness: { p90Min: 35, flatShareMax: 0.1 } }, ROCK_LIKE)[0]?.pass).toBe(false);
    expect(judged({ class: "rock", surfaceRoughness: { p90Min: 25, flatShareMax: 0.01 } }, ROCK_LIKE)[0]?.pass).toBe(false);
  });

  it("fail with a null measurement when a value could not be measured", () => {
    const missing: NaturalMeasurements = {
      silhouettes: { size: 1024, views: {}, dimension: null, solidity: null, failure: "the natural silhouettes did not render: timeout" },
      surfaceRoughness: { ...ROCK_LIKE.surfaceRoughness!, lowestP90: null, highestFlatShare: null },
      albedoVariation: { cv: null, texels: 0, mean: null, images: [], untexturedShare: 1 },
    };
    const results = judged({ class: "rock", silhouetteDimension: { min: 0 }, solidity: { max: 1 }, surfaceRoughness: { p90Min: 0, flatShareMax: 1 }, albedoVariation: { min: 0 } }, missing);
    expect(results.map((result) => result.pass)).toEqual([false, false, false, false]);
    expect(results[0]?.measured).toMatchObject({ lowest: null, failure: "the natural silhouettes did not render: timeout" });
    expect(judged({ class: "rock", albedoVariation: { min: 0 } }, undefined)[0]).toMatchObject({ measured: { cv: null }, pass: false });
  });

  it("print one natural line in the summary", () => {
    expect(naturalLines(ROCK_LIKE)).toEqual(["  natural: silhouettes 1024 px: no views; roughness over 2 objects: lowest p90 30 deg, highest flat share 0.05; albedo CV 0.3 over 1000 texels of 0 images"]);
    expect(naturalLines(undefined)).toEqual([]);
  });
});

describe("the one judge pass with natural rules", () => {
  const delivery = { folder: "/delivery", main: "/delivery/rock.glb", files: [], bytes: 1, sha256: "0".repeat(64), references: { files: 0, unresolved: [] } };
  const plan = (natural: Record<string, unknown>) =>
    planPass({ spec: parseSpec({ format: "glb", natural }), delivery, references: null, maxTriangles: 1000, timeoutMs: 1000, mode: "cpu", render: {}, visual: {} });

  it("renders the 1024 px silhouettes in the reference stage only when a silhouette rule asks for them", () => {
    const silhouettes = plan({ class: "rock", solidity: { max: 0.9 } });
    expect(silhouettes.stages).toEqual(["measure", "reference", "views", "sheet"]);
    expect(silhouettes.args.join(" ")).toContain("--natural-views front:1024,right:1024,top:1024");
    expect(silhouettes.args).not.toContain("--natural");
    const measured = plan({ class: "rock", surfaceRoughness: { p90Min: 10 }, albedoVariation: { min: 0.1 } });
    expect(measured.stages).toEqual(["measure", "views", "sheet"]);
    expect(measured.args.join(" ")).toContain("--natural roughness,albedo");
    expect(measured.args).not.toContain("--natural-views");
  });

  it("covers the natural silhouettes with the reference stage's checksum", () => {
    const out = freshDir("natural-rules", "digest");
    mkdirSync(join(out, "silhouettes"));
    writeFileSync(join(out, "silhouettes.json"), "{}");
    writeFileSync(join(out, "silhouettes", "natural-front.png"), "a");
    const before = stageDigest(out, "reference");
    writeFileSync(join(out, "silhouettes", "natural-front.png"), "b");
    expect(stageDigest(out, "reference")).not.toBe(before);
  });
});
