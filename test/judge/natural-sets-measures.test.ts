import { describe, expect, it } from "vitest";
import { DELTA_CEILING, solveDelta, summarizeDeltas } from "../../src/judge/natural-leonardo.js";
import { expectedLog, fitPowerLaw, MIN_TAIL, powerCdf } from "../../src/judge/natural-power.js";
import { leonardo, sizeDistribution } from "../../src/judge/natural-sets.js";

function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return (state + 0.5) / 2 ** 32;
  };
}

function pareto(count: number, exponent: number, low: number, seed: number): number[] {
  const next = random(seed);
  return Array.from({ length: count }, () => low * (1 - next()) ** (1 / (exponent + 1)));
}

describe("natural.sizeDistribution: a maximum-likelihood power-law fit with a fitted minimum", () => {
  it("fits 2,000 sizes drawn from a power law with exponent -2 within 0.15, for several draws", () => {
    for (const seed of [1, 2, 3, 4, 5, 6]) {
      const fit = fitPowerLaw(pareto(2000, -2, 1, seed));
      expect(Math.abs(fit.exponent! + 2), `seed ${seed}`).toBeLessThan(0.15);
      expect(fit.xMin).toBeGreaterThanOrEqual(1);
      expect(fit.tail).toBeGreaterThanOrEqual(MIN_TAIL);
    }
  });

  it("fits a power law cut at both ends, as a scatter draws its scales, without the bias of an open-ended fit", () => {
    const next = random(9);
    const sizes = Array.from({ length: 400 }, () => (0.3 ** -1 + next() * (2.4 ** -1 - 0.3 ** -1)) ** -1);
    expect(Math.abs(fitPowerLaw(sizes).exponent! + 2)).toBeLessThan(0.25);
  });

  it("gives uniform sizes an exponent far outside the band [-2.5, -1.5]", () => {
    const next = random(11);
    const fit = fitPowerLaw(Array.from({ length: 2000 }, () => 1 + next()));
    expect(fit.exponent! > -1.5 || fit.exponent! < -2.5).toBe(true);
  });

  it("refuses to fit fewer than 50 sizes or sizes that are all the same", () => {
    expect(fitPowerLaw(pareto(MIN_TAIL - 1, -2, 1, 3))).toMatchObject({ exponent: null, failure: expect.stringContaining("fewer than the 50") });
    expect(fitPowerLaw(Array(200).fill(0.5))).toMatchObject({ exponent: null, failure: expect.stringContaining("all the same") });
  });

  it("uses a model whose mean log and distribution function agree with hand-worked values", () => {
    expect(expectedLog(-1, 1, Math.E ** 2)).toBeCloseTo(1, 12);
    expect(expectedLog(-2, 1, 8)).toBeCloseTo((8 / 7) * (1 - 0.125 - Math.log(8) / 8), 9);
    expect(powerCdf(2, -2, 1, 4)).toBeCloseTo((1 - 1 / 2) / (1 - 1 / 4), 12);
    expect(powerCdf(4, 0, 2, 6)).toBeCloseTo(0.5, 12);
  });

  it("reports the fit in place of the sizes, and keeps a failure from the measure stage", () => {
    const fitted = sizeDistribution({ by: "sphere", objects: "*", sizes: pareto(300, -2, 0.1, 4), unmeasured: 0, failure: null });
    expect(fitted).toMatchObject({ by: "sphere", count: 300, failure: null });
    expect(fitted).not.toHaveProperty("sizes");
    expect(sizeDistribution({ by: "trunk", objects: "*", sizes: [], unmeasured: 0, failure: "no skeleton" })).toMatchObject({ exponent: null, failure: "no skeleton" });
  });
});

describe("natural.leonardo: Δ from d^Δ = Σ d_i^Δ at each branching", () => {
  it("solves Δ = 2 and Δ = 3 from radii made with them", () => {
    expect(solveDelta(1, [Math.sqrt(0.5), Math.sqrt(0.5)])!.delta).toBeCloseTo(2, 9);
    expect(solveDelta(2, [2 * 0.7 ** (1 / 3), 2 * 0.3 ** (1 / 3)])!.delta).toBeCloseTo(3, 9);
    expect(solveDelta(1, [0.6 ** 0.5, 0.3 ** 0.5, 0.1 ** 0.5])!.delta).toBeCloseTo(2, 9);
  });

  it("puts a child as thick as its parent at the ceiling, above every limit", () => {
    expect(solveDelta(1, [1, 1])).toEqual({ delta: DELTA_CEILING, above: true });
    expect(solveDelta(1, [0.9999999, 0.9999999])).toEqual({ delta: DELTA_CEILING, above: true });
    expect(solveDelta(0, [1, 1])).toBeNull();
  });

  it("takes the median over the branchings", () => {
    const summary = summarizeDeltas([
      [1, Math.sqrt(0.5), Math.sqrt(0.5)],
      [1, 0.8 ** (1 / 3), 0.2 ** (1 / 3)],
      [1, 1, 1],
    ]);
    expect(summary).toMatchObject({ median: 3, solved: 2, above: 1, invalid: 0 });
  });

  it("reports null with the failure when no skeleton was found or none could be measured", () => {
    expect(leonardo({ skeletons: [], refused: [], failure: "no object carries a blendworks.skeleton skeleton" })).toMatchObject({ median: null, failure: "no object carries a blendworks.skeleton skeleton" });
    const unmeasured = leonardo({ skeletons: [{ object: "tree", nodes: 9, exponent: 2, branchings: 3, sampled: 3, unmeasured: 3, radii: [] }], refused: [], failure: null });
    expect(unmeasured).toMatchObject({ median: null, unmeasured: 3, failure: "no branching of the skeleton could be measured on the mesh" });
  });
});
