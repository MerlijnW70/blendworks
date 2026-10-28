import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { isInfrastructure } from "./infrastructure.js";
import { boxCountingDimension, solidity } from "./natural-measures.js";
import { atLeast, atMost, rangeChecks, setChecks, setLines, type Check } from "./natural-checks.js";
import type { NaturalMeasurements, NaturalSilhouettes } from "./natural-schema.js";
import { naturalLimits, NATURAL_RULES, wantsNaturalSilhouettes, type NaturalLimits, type NaturalRule, type NaturalRuleName } from "./natural-spec.js";
import type { PassResult } from "./onepass.js";
import { silhouettesFrom } from "./reference.js";
import type { RuleResult } from "./shape-rules.js";
import { readShared } from "./shared-access.js";
import { maskFromPixels, maskImage } from "./silhouette.js";
import { StageFailure, workOut, type Sandbox } from "./stages.js";
import { decodePng, encodePng } from "./visual/png.js";

export const NATURAL_SILHOUETTE_SIZE = 1024;
export const NATURAL_PREFIX = "natural-";
export const NATURAL_FOLDER = "natural";
export const DIMENSION_VIEWS = ["front", "right"] as const;
export const SOLIDITY_VIEWS = ["front", "right", "top"] as const;

export function naturalViewArgs(rule: NaturalRule | undefined): string[] {
  if (!wantsNaturalSilhouettes(rule)) return [];
  return ["--natural-views", SOLIDITY_VIEWS.map((view) => `${view}:${NATURAL_SILHOUETTE_SIZE}`).join(",")];
}

function lowest(values: (number | null | undefined)[]): number | null {
  if (values.some((value) => value === null || value === undefined)) return null;
  return Math.min(...(values as number[]));
}

function failed(message: string): NaturalSilhouettes {
  return { size: NATURAL_SILHOUETTE_SIZE, views: {}, dimension: null, solidity: null, failure: message };
}

export function naturalSilhouettes(result: PassResult, sandbox: Sandbox, outDir: string): NaturalSilhouettes {
  let rendered;
  try {
    rendered = silhouettesFrom(result, sandbox).natural;
  } catch (error) {
    if (error instanceof StageFailure && !isInfrastructure(error.failure)) return failed(`the natural silhouettes did not render: ${error.failure.message}`);
    throw error;
  }
  if (rendered === undefined) return failed("the reference stage rendered no natural silhouettes");
  const views: NaturalSilhouettes["views"] = {};
  const folder = join(outDir, NATURAL_FOLDER);
  mkdirSync(folder, { recursive: true });
  for (const entry of rendered) {
    const mask = maskFromPixels(decodePng(readShared(join(workOut(sandbox), "silhouettes", `${NATURAL_PREFIX}${entry.view}.png`))), "alpha");
    const data = encodePng(maskImage(mask));
    writeFileSync(join(folder, `${entry.view}-silhouette.png`), data);
    const boxes = boxCountingDimension(mask);
    const filled = solidity(mask);
    views[entry.view] = {
      dimension: boxes.dimension,
      boxCounts: boxes.counts,
      edgePixels: boxes.edgePixels,
      solidity: filled.solidity,
      area: filled.area,
      hullArea: filled.hullArea,
      sha256: createHash("sha256").update(data).digest("hex"),
    };
  }
  return {
    size: NATURAL_SILHOUETTE_SIZE,
    views,
    dimension: lowest(DIMENSION_VIEWS.map((view) => views[view]?.dimension)),
    solidity: lowest(SOLIDITY_VIEWS.map((view) => views[view]?.solidity)),
    failure: null,
  };
}


function checks(name: NaturalRuleName, limits: NaturalLimits, natural: NaturalMeasurements | undefined): { measured: Record<string, unknown>; checks: Check[] } {
  if (name === "silhouetteDimension") {
    const silhouettes = natural?.silhouettes;
    const value = silhouettes?.dimension ?? null;
    return { measured: { lowest: value, views: Object.fromEntries(DIMENSION_VIEWS.map((view) => [view, silhouettes?.views[view]?.dimension ?? null])), ...failure(silhouettes) }, checks: rangeChecks(value, limits) };
  }
  if (name === "solidity") {
    const silhouettes = natural?.silhouettes;
    const value = silhouettes?.solidity ?? null;
    return { measured: { lowest: value, views: Object.fromEntries(SOLIDITY_VIEWS.map((view) => [view, silhouettes?.views[view]?.solidity ?? null])), ...failure(silhouettes) }, checks: rangeChecks(value, limits) };
  }
  if (name === "surfaceRoughness") {
    const roughness = natural?.surfaceRoughness;
    const p90 = roughness?.lowestP90 ?? null;
    const flat = roughness?.highestFlatShare ?? null;
    return {
      measured: { lowestP90: p90, highestFlatShare: flat, objects: roughness?.objects ?? 0 },
      checks: [
        ...(limits.p90Min === undefined ? [] : [{ name: "p90Min", measured: p90, limit: limits.p90Min, pass: atLeast }]),
        ...(limits.flatShareMax === undefined ? [] : [{ name: "flatShareMax", measured: flat, limit: limits.flatShareMax, pass: atMost }]),
      ],
    };
  }
  if (name === "albedoVariation") {
    const albedo = natural?.albedoVariation;
    const value = albedo?.cv ?? null;
    return { measured: { cv: value, texels: albedo?.texels ?? 0, images: albedo?.images.length ?? 0 }, checks: rangeChecks(value, limits) };
  }
  return setChecks(name, limits, natural);
}

function failure(silhouettes: NaturalSilhouettes | undefined): Record<string, string> {
  return silhouettes?.failure ? { failure: silhouettes.failure } : {};
}

export const RENDERED_RULES: readonly NaturalRuleName[] = ["repetition"];
const MEASURED_RULES = NATURAL_RULES.filter((name) => !RENDERED_RULES.includes(name));

export function naturalRules(rule: NaturalRule | undefined, natural: NaturalMeasurements | undefined, names: readonly NaturalRuleName[] = MEASURED_RULES): RuleResult[] {
  if (rule === undefined) return [];
  const results: RuleResult[] = [];
  for (const name of names) {
    const resolved = naturalLimits(rule, name);
    if (resolved === undefined) continue;
    const found = checks(name, resolved.limits, natural);
    const pass = found.checks.length > 0 && found.checks.every((check) => check.measured !== null && check.pass(check.measured, check.limit));
    const limit = { ...resolved.limits, ...resolved.options, class: rule.class, source: resolved.source, ...(resolved.cites === undefined ? {} : { cites: resolved.cites }) };
    results.push({ rule: `natural.${name}`, measured: found.measured, limit, pass });
  }
  return results;
}

function shown(value: number | null | undefined): string {
  return value === null || value === undefined ? "none" : String(value);
}

export function naturalLines(natural: NaturalMeasurements | undefined): string[] {
  if (natural === undefined) return [];
  const parts: string[] = [];
  const { silhouettes, surfaceRoughness, albedoVariation } = natural;
  if (silhouettes) {
    const views = Object.entries(silhouettes.views).map(([view, entry]) => `${view} D ${shown(entry.dimension)} solidity ${shown(entry.solidity)}`);
    parts.push(`silhouettes ${silhouettes.size} px: ${silhouettes.failure ?? (views.length === 0 ? "no views" : views.join(", "))}`);
  }
  if (surfaceRoughness) parts.push(`roughness over ${surfaceRoughness.objects} objects: lowest p90 ${shown(surfaceRoughness.lowestP90)} deg, highest flat share ${shown(surfaceRoughness.highestFlatShare)}`);
  if (albedoVariation) parts.push(`albedo CV ${shown(albedoVariation.cv)} over ${albedoVariation.texels} texels of ${albedoVariation.images.length} images`);
  parts.push(...setLines(natural));
  return parts.length === 0 ? [] : [`  natural: ${parts.join("; ")}`];
}
