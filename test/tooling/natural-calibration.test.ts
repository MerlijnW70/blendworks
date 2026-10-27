import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { NATURAL_DEFAULTS } from "../../src/judge/natural-defaults.js";
import { NATURAL_CLASSES } from "../../src/judge/natural-spec.js";
import { defaultsFrom, defaultsSource, deriveThreshold, MEASURES, MIN_PER_CLASS, percentile, proceduralScores, SCANS, thresholds, type Measure } from "../../scripts/lib/natural-calibration.js";
import { calibrationMarkdown, DOC_END, DOC_START, replaceCalibration, type CalibrationDocument } from "../../scripts/lib/natural-calibration-doc.js";
import { plannedRecipes, PROCEDURAL } from "../../scripts/lib/natural-sources.js";
import { repoRoot } from "../../scripts/lib/paths.js";

const LOWER: Measure = MEASURES.find((measure) => measure.key === "p90")!;
const UPPER: Measure = MEASURES.find((measure) => measure.key === "solidity")!;

describe("the calibration's threshold rule", () => {
  it("takes percentiles by linear interpolation between ranks", () => {
    expect(percentile([10, 20, 30, 40, 50], 50)).toBe(30);
    expect(percentile([10, 20, 30, 40, 50], 5)).toBeCloseTo(12, 9);
    expect(percentile([50, 10, 40, 20, 30], 95)).toBeCloseTo(48, 9);
  });

  it("puts a lower limit midway between the scans' 5th percentile and the highest stand-in when they do not overlap", () => {
    const found = deriveThreshold(LOWER, "rock", [10, 20, 30, 40, 50], [2, 6]);
    expect(found).toMatchObject({ realP5: 12, worstStandIn: 6, threshold: 9, separates: true, realPassShare: 1, standInFailShare: 1 });
  });

  it("puts an upper limit midway between the scans' 95th percentile and the lowest stand-in", () => {
    const found = deriveThreshold(UPPER, "rock", [0.5, 0.6, 0.7, 0.8, 0.9], [0.99, 1]);
    expect(found).toMatchObject({ realP5: 0.88, worstStandIn: 0.99, threshold: 0.935, separates: true });
  });

  it("falls back to the percentile and reports no separation when a stand-in reaches the scans", () => {
    const found = deriveThreshold(LOWER, "rock", [10, 20, 30, 40, 50], [2, 15]);
    expect(found).toMatchObject({ realP5: 12, worstStandIn: 15, threshold: 12, separates: false, standInFailShare: 0.5 });
    expect(found.rule).toBe("5th percentile of the scans");
  });

  it("does not count a separation when no stand-in has a value", () => {
    const found = deriveThreshold(LOWER, "rock", [10, 20, 30, 40, 50], [null]);
    expect(found).toMatchObject({ threshold: 12, separates: false, standInsMeasured: 0, standInFailShare: 1 });
  });

  it("does not count a separation smaller than the measure's step", () => {
    const dimension = MEASURES.find((measure) => measure.key === "dimension")!;
    expect(deriveThreshold(dimension, "rock", [1.004, 1.02, 1.03], [1.0, 0.99])).toMatchObject({ worstStandIn: 1, separates: false });
    expect(deriveThreshold(dimension, "plant", [1.3, 1.4, 1.5], [1.21])).toMatchObject({ threshold: 1.26, separates: true });
  });

  it("makes defaults only from separating measures", () => {
    const assets = [
      ...[10, 20, 30, 40, 50].map((value, index) => ({ id: `scan-${index}`, kind: "scan" as const, classes: ["rock" as const], values: { p90: value, flatShare: 0.1, solidity: 0.8 } })),
      { id: "sphere", kind: "stand-in" as const, classes: ["rock" as const], values: { p90: 2, flatShare: 0.05, solidity: 1 } },
    ];
    const defaults = defaultsFrom(thresholds(assets));
    expect(defaults.rock).toEqual({ surfaceRoughness: { p90Min: 7 }, solidity: { max: 0.9 } });
    expect(defaults.tree).toEqual({});
    expect(defaultsSource(defaults)).toContain("rock: { solidity: { max: 0.9 }, surfaceRoughness: { p90Min: 7 } },");
  });
});

describe("the pinned calibration set", () => {
  it("lists at least 30 scans, at least 8 of each class, each once", () => {
    expect(SCANS.length).toBeGreaterThanOrEqual(30);
    for (const kind of NATURAL_CLASSES) expect(SCANS.filter((scan) => scan.class === kind).length, kind).toBeGreaterThanOrEqual(MIN_PER_CLASS);
    expect(new Set(SCANS.map((scan) => scan.id)).size).toBe(SCANS.length);
  });

  it("builds the noise_displace rocks only when the bridge has every command they use, and says what is missing", () => {
    const every = new Set(PROCEDURAL.flatMap((recipe) => recipe.commands));
    expect(every.has("noise_displace")).toBe(true);
    expect(plannedRecipes(every)).toEqual({ build: PROCEDURAL, skipped: [] });
    const without = new Set([...every].filter((command) => command !== "noise_displace"));
    const planned = plannedRecipes(without);
    expect(planned.build).toEqual([]);
    expect(planned.skipped.map((entry) => entry.reason)).toEqual(PROCEDURAL.map(() => "the bridge on this main has no noise_displace"));
  });

  it("scores procedural assets against the defaults without letting them set a threshold", () => {
    const assets = [
      ...[10, 20, 30, 40, 50].map((value, index) => ({ id: `scan-${index}`, kind: "scan" as const, classes: ["rock" as const], values: { p90: value } })),
      { id: "sphere", kind: "stand-in" as const, classes: ["rock" as const], values: { p90: 2 } },
      { id: "noise", kind: "procedural" as const, classes: ["rock" as const], values: { p90: 11 } },
    ];
    const found = thresholds(assets);
    expect(found.find((entry) => entry.class === "rock" && entry.measure === "p90")).toMatchObject({ threshold: 7, separates: true, standIns: 1 });
    expect(proceduralScores(assets, defaultsFrom(found))).toEqual([{ id: "noise", class: "rock", limits: [{ limit: "natural.surfaceRoughness.p90Min", threshold: 7, value: 11, pass: true }], passes: true }]);
  });
});

describe("the committed calibration", () => {
  const document = JSON.parse(readFileSync(join(repoRoot, "docs", "research", "natural-shapes", "calibration.json"), "utf8")) as CalibrationDocument;

  it("records every scan with its class, source page, licence and values", () => {
    const scans = document.assets.filter((asset) => asset.kind === "scan");
    expect(scans.map((asset) => asset.id).sort()).toEqual(SCANS.map((scan) => scan.id).sort());
    for (const asset of scans) {
      expect(asset.source).toBe(`https://polyhaven.com/a/${asset.id}`);
      expect(asset.licence).toBe("CC0-1.0");
      expect(asset.failure).toBeNull();
      expect(Object.keys(asset.values).sort()).toEqual(MEASURES.map((measure) => measure.key).sort());
    }
  });

  it("derives its thresholds and defaults by the stated rule from its own values", () => {
    expect(document.thresholds).toEqual(thresholds(document.assets));
    expect(document.defaults).toEqual(defaultsFrom(document.thresholds));
    expect(document.proceduralScores).toEqual(proceduralScores(document.assets, document.defaults));
    expect(document.procedural).toEqual(PROCEDURAL.map((recipe) => ({ id: recipe.id, status: "built", reason: null })));
  });

  it("is the source of the judge's defaults", () => {
    expect(NATURAL_DEFAULTS).toEqual(document.defaults);
    expect(readFileSync(join(repoRoot, "src", "judge", "natural-defaults.ts"), "utf8").replace(/\r\n/g, "\n")).toBe(defaultsSource(document.defaults));
  });

  it("is the table in natural-shapes.md", () => {
    const markdown = readFileSync(join(repoRoot, "docs", "research", "natural-shapes.md"), "utf8").replace(/\r\n/g, "\n");
    const block = markdown.slice(markdown.indexOf(DOC_START), markdown.indexOf(DOC_END) + DOC_END.length);
    expect(block).toBe(calibrationMarkdown(document));
    expect(replaceCalibration(markdown, calibrationMarkdown(document))).toBe(markdown);
  });
});
