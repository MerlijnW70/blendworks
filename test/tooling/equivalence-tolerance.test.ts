import { describe, expect, it } from "vitest";
import { differences, EXACT, PLATFORM_NOISE } from "../../scripts/lib/equivalence.js";

function report(overrides: { sizeX?: number; boundsMin?: number; coverage?: number; pass?: boolean; triangles?: number } = {}) {
  return {
    passed: false,
    rules: [
      { rule: "triangles.max", measured: overrides.triangles ?? 7616, limit: 5000, pass: false },
      { rule: "size.x", measured: overrides.sizeX ?? 0.686702, limit: [0.95, 1.05], pass: overrides.pass ?? false },
      { rule: "uv.minCoverage", measured: overrides.coverage ?? 0.056252, limit: 0.1, pass: false },
    ],
    measurements: {
      bounds: { min: [-0.343351, overrides.boundsMin ?? -0.429227, 0], max: [0.343351, 0.2, 1.7] },
      size: [overrides.sizeX ?? 0.686702, 0.629227, 1.7],
      uv: { coverage: overrides.coverage ?? 0.056252 },
      objectList: { items: [{ bounds: { min: [-0.343351, overrides.boundsMin ?? -0.429227, 0], max: [0.343351, 0.2, 1.7] }, size: [overrides.sizeX ?? 0.686702, 0.629227, 1.7] }] },
    },
  };
}

describe("comparing judge reports across platforms", () => {
  it("lets a position-derived value move by one unit of its sixth decimal and no more", () => {
    expect(differences(report(), report({ sizeX: 0.686701, boundsMin: -0.429226 }), PLATFORM_NOISE)).toEqual([]);
    expect(differences(report(), report({ sizeX: 0.686703 }), PLATFORM_NOISE)).toEqual([]);
    expect(differences(report(), report({ sizeX: 0.6867 }), PLATFORM_NOISE)).toEqual([
      "/rules/1/measured: 0.686702 became 0.6867",
      "/measurements/size/0: 0.686702 became 0.6867",
      "/measurements/objectList/items/0/size/0: 0.686702 became 0.6867",
    ]);
    expect(differences(report(), report({ boundsMin: -0.429229 }), PLATFORM_NOISE)).toEqual([
      "/measurements/bounds/min/1: -0.429227 became -0.429229",
      "/measurements/objectList/items/0/bounds/min/1: -0.429227 became -0.429229",
    ]);
  });

  it("compares every other field exactly: counts, verdicts and values not read from vertex positions", () => {
    expect(differences(report(), report({ coverage: 0.056253 }), PLATFORM_NOISE)).toEqual(["/rules/2/measured: 0.056252 became 0.056253", "/measurements/uv/coverage: 0.056252 became 0.056253"]);
    expect(differences(report(), report({ triangles: 7617 }), PLATFORM_NOISE)).toEqual(["/rules/0/measured: 7616 became 7617"]);
    expect(differences(report(), report({ sizeX: 0.686701, pass: true }), PLATFORM_NOISE)).toEqual(["/rules/1/pass: false became true"]);
  });

  it("is exact unless the noise tolerance is asked for", () => {
    expect(differences(report(), report({ sizeX: 0.686701 }))).toHaveLength(3);
    expect(differences(report(), report({ sizeX: 0.686701 }), EXACT)).toHaveLength(3);
    expect(differences(report(), report())).toEqual([]);
  });
});
