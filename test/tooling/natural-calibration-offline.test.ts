import { copyFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { defaultsFrom, deriveThreshold, MEASURES, PERCENTILES, percentile, thresholds } from "../../scripts/lib/natural-calibration.js";
import { DOC_END, DOC_START, type CalibrationDocument } from "../../scripts/lib/natural-calibration-doc.js";
import { runCalibration, standInInputs, writeCalibration, type CalibrationInput } from "../../scripts/lib/natural-calibration-run.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { freshDir, makeFixtureSet } from "../judge/helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let first: CalibrationDocument;
let second: CalibrationDocument;
let markdown = "";
let written: CalibrationDocument;
let defaults = "";

beforeAll(withWorkBudget(400_000, async () => {
  const assets = makeFixtureSet("natural_fixtures", "natural-calibration").assets;
  const out = freshDir("natural-calibration", "out");
  const local = (id: string, kind: "rock" | "plant"): CalibrationInput => ({ id, kind: "scan", classes: [kind], path: join(assets, `${id}.glb`), source: join(assets, `${id}.glb`), licence: "local" });
  const inputs = [local("rough-rock", "rock"), local("leaf-cloud", "plant"), ...standInInputs(assets)];
  const run = (dir: string) => runCalibration({ inputs, procedural: [{ id: "noise-rock", status: "skipped", reason: "offline" }], workDir: freshDir("natural-calibration", dir), blender: "5.2.3", resolution: "1k", exclusive: (task) => task() });
  first = await run("first");
  second = await run("second");
  const doc = join(out, "natural-shapes.md");
  copyFileSync(join(repoRoot, "docs", "research", "natural-shapes.md"), doc);
  writeCalibration(first, { json: join(out, "calibration.json"), doc, defaults: join(out, "natural-defaults.ts") });
  markdown = readFileSync(doc, "utf8");
  written = JSON.parse(readFileSync(join(out, "calibration.json"), "utf8")) as CalibrationDocument;
  defaults = readFileSync(join(out, "natural-defaults.ts"), "utf8");
}));

describe("the calibration on generated stand-ins, offline", workBudget(60_000), () => {
  it("measures every asset and gives the same values on a second run", () => {
    expect(first.assets.map((asset) => asset.failure)).toEqual(first.assets.map(() => null));
    expect(first.assets.map((asset) => asset.values)).toEqual(second.assets.map((asset) => asset.values));
    expect(JSON.stringify(first)).toBe(JSON.stringify(second));
  });

  it("writes a percentile table per class with the 5th, 25th, 50th, 75th and 95th percentiles", () => {
    const block = markdown.slice(markdown.indexOf(DOC_START), markdown.indexOf(DOC_END));
    expect(block).toContain(`| Class | Measure | n | ${PERCENTILES.map((p) => `P${p}`).join(" | ")} |`);
    for (const kind of ["rock", "tree", "plant"]) for (const measure of MEASURES) expect(block).toContain(`| ${kind} | ${measure.label} |`);
    const rock = first.assets.find((asset) => asset.id === "rough-rock")!;
    expect(block).toContain(`| rock | ${MEASURES[1]!.label} | 1 | ${PERCENTILES.map(() => rock.values["solidity"]!.toFixed(4)).join(" | ")} |`);
    expect(block).toContain("| clouds-ico (stand-in) | rock |");
    expect(block).toContain("| noise-rock (procedural) | not built: offline |");
    expect(markdown.indexOf("### 2.8 Calibration set (P12)")).toBeLessThan(markdown.indexOf(DOC_START));
  });

  it("derives each threshold by the stated rule from the measured values", () => {
    expect(written).toEqual(first);
    for (const entry of first.thresholds) {
      const measure = MEASURES.find((candidate) => candidate.key === entry.measure)!;
      const scans = first.assets.filter((asset) => asset.kind === "scan" && asset.classes.includes(entry.class)).map((asset) => asset.values[measure.key] ?? null);
      const standIns = first.assets.filter((asset) => asset.kind === "stand-in" && asset.classes.includes(entry.class)).map((asset) => asset.values[measure.key] ?? null);
      expect(entry).toEqual(deriveThreshold(measure, entry.class, scans, standIns));
    }
    const solidity = first.thresholds.find((entry) => entry.class === "rock" && entry.measure === "solidity")!;
    const rock = first.assets.find((asset) => asset.id === "rough-rock")!.values["solidity"]!;
    const nearest = Math.min(...first.assets.filter((asset) => asset.kind === "stand-in" && asset.classes.includes("rock")).map((asset) => asset.values["solidity"]!));
    expect(solidity.realP5).toBeCloseTo(percentile([rock], 95), 6);
    expect(solidity.threshold).toBeCloseTo((rock + nearest) / 2, 3);
    expect(first.defaults).toEqual(defaultsFrom(thresholds(first.assets)));
    expect(defaults).toContain("export const NATURAL_DEFAULTS = {");
  });
});
