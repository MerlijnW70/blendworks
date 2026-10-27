import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";
import type { NaturalMeasurements } from "../../src/judge/natural-schema.js";
import { calibratedLimits, NATURAL_CLASSES, NATURAL_RULES, type NaturalClass } from "../../src/judge/natural-spec.js";
import { judge } from "../../src/judge/run.js";
import { classPercentiles, defaultsFrom, defaultsSource, MEASURES, proceduralScores, STAND_INS, thresholds, type MeasuredAsset, type Values } from "./natural-calibration.js";
import { calibrationMarkdown, replaceCalibration, THRESHOLD_RULE, type CalibratedAsset, type CalibrationDocument, type ProceduralRecord } from "./natural-calibration-doc.js";

export type Exclusive = <T>(task: () => Promise<T>) => Promise<T>;

export type CalibrationInput = { id: string; kind: MeasuredAsset["kind"]; classes: NaturalClass[]; path: string; source: string; licence: string };

const MEASURING_SPEC = {
  silhouetteDimension: { min: 0 },
  solidity: { max: 1 },
  surfaceRoughness: { p90Min: 0 },
  albedoVariation: { min: 0 },
};

export function valuesOf(natural: NaturalMeasurements | undefined): Values {
  return {
    dimension: natural?.silhouettes?.dimension ?? null,
    solidity: natural?.silhouettes?.solidity ?? null,
    p90: natural?.surfaceRoughness?.lowestP90 ?? null,
    flatShare: natural?.surfaceRoughness?.highestFlatShare ?? null,
    albedoCv: natural?.albedoVariation?.cv ?? null,
  };
}

export async function measureAsset(input: CalibrationInput, workDir: string, exclusive: Exclusive): Promise<CalibratedAsset> {
  const folder = join(workDir, `${input.kind}-${input.id}`);
  mkdirSync(folder, { recursive: true });
  const specPath = join(folder, "spec.json");
  const format = extname(input.path).slice(1).toLowerCase();
  writeFileSync(specPath, `${JSON.stringify({ name: input.id, format, natural: { class: input.classes[0], ...MEASURING_SPEC } }, null, 2)}\n`);
  const report = await exclusive(() => judge({ specPath, assetPath: input.path, outDir: join(folder, "judged"), preview: true }));
  const natural = report.measurements?.natural;
  return {
    id: input.id,
    kind: input.kind,
    classes: input.classes,
    source: input.source,
    licence: input.licence,
    setSha256: report.asset.setSha256,
    values: valuesOf(natural),
    natural: natural ?? null,
    failure: report.failure === null ? null : `${report.failure.stage}: ${report.failure.message}`,
  };
}

export function standInInputs(folder: string): CalibrationInput[] {
  return STAND_INS.map((standIn) => ({
    id: standIn.id,
    kind: "stand-in",
    classes: [...standIn.classes],
    path: join(folder, `${standIn.id}.glb`),
    source: `test/judge/natural_fixtures.py: ${standIn.description}`,
    licence: "generated",
  }));
}

export type CalibrationRun = { inputs: CalibrationInput[]; procedural: ProceduralRecord[]; workDir: string; blender: string; resolution: string; exclusive: Exclusive; log?: (line: string) => void };

export async function runCalibration(run: CalibrationRun): Promise<CalibrationDocument> {
  const assets: CalibratedAsset[] = [];
  for (const input of run.inputs) {
    const started = performance.now();
    const measured = await measureAsset(input, run.workDir, run.exclusive);
    run.log?.(`${input.kind} ${input.id}: ${MEASURES.map((measure) => `${measure.key} ${measured.values[measure.key] ?? "n/a"}`).join(", ")}${measured.failure ? ` (${measured.failure})` : ""} in ${((performance.now() - started) / 1000).toFixed(1)} s`);
    assets.push(measured);
  }
  const found = thresholds(assets);
  const defaults = defaultsFrom(found);
  return {
    version: 1,
    blender: run.blender,
    resolution: run.resolution,
    thresholdRule: THRESHOLD_RULE,
    assets,
    procedural: run.procedural,
    percentiles: Object.fromEntries(NATURAL_CLASSES.map((kind) => [kind, classPercentiles(assets, kind)])) as CalibrationDocument["percentiles"],
    thresholds: found,
    defaults,
    proceduralScores: proceduralScores(assets, defaults),
  };
}

export type Outputs = { json: string; doc: string; defaults: string };

export function writeCalibration(document: CalibrationDocument, outputs: Outputs): void {
  writeFileSync(outputs.json, `${JSON.stringify(document, null, 2)}\n`);
  writeFileSync(outputs.doc, replaceCalibration(readFileSync(outputs.doc, "utf8"), calibrationMarkdown(document)));
  writeFileSync(outputs.defaults, defaultsSource(document.defaults));
}

export type Verified = { id: string; kind: CalibrationInput["kind"]; class: NaturalClass; passed: boolean; rules: { rule: string; pass: boolean; measured: unknown }[] };

export function defaultsSpec(kind: NaturalClass, format: string): Record<string, unknown> {
  const rules = NATURAL_RULES.filter((rule) => calibratedLimits(kind, rule) !== undefined);
  return { name: `natural ${kind} defaults`, format, natural: { class: kind, ...Object.fromEntries(rules.map((rule) => [rule, {}])) } };
}

export async function verifyDefaults(inputs: CalibrationInput[], workDir: string, exclusive: Exclusive): Promise<Verified[]> {
  const verified: Verified[] = [];
  for (const input of inputs) {
    const kind = input.classes[0]!;
    const folder = join(workDir, `verify-${input.kind}-${input.id}`);
    mkdirSync(folder, { recursive: true });
    const specPath = join(folder, "spec.json");
    writeFileSync(specPath, `${JSON.stringify(defaultsSpec(kind, extname(input.path).slice(1).toLowerCase()), null, 2)}
`);
    const report = await exclusive(() => judge({ specPath, assetPath: input.path, outDir: join(folder, "judged"), preview: true }));
    verified.push({ id: input.id, kind: input.kind, class: kind, passed: report.passed, rules: report.rules.map((rule) => ({ rule: rule.rule, pass: rule.pass, measured: rule.measured })) });
  }
  return verified;
}
