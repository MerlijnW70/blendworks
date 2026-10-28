import type { NaturalMeasurements } from "./natural-schema.js";
import type { NaturalLimits, NaturalRuleName } from "./natural-spec.js";

export type Check = { name: string; measured: number | null; limit: number; pass: (value: number, limit: number) => boolean };

export const atLeast = (value: number, limit: number) => value >= limit;
export const atMost = (value: number, limit: number) => value <= limit;

export function rangeChecks(measured: number | null, limits: NaturalLimits): Check[] {
  return [
    ...(limits.min === undefined ? [] : [{ name: "min", measured, limit: limits.min, pass: atLeast }]),
    ...(limits.max === undefined ? [] : [{ name: "max", measured, limit: limits.max, pass: atMost }]),
  ];
}

function failed(failure: string | null | undefined, missing: string): Record<string, string> {
  if (failure) return { failure };
  return failure === undefined ? { failure: missing } : {};
}

export function setChecks(name: NaturalRuleName, limits: NaturalLimits, natural: NaturalMeasurements | undefined): { measured: Record<string, unknown>; checks: Check[] } {
  if (name === "repetition") {
    const found = natural?.repetition;
    const value = found?.worst ?? null;
    const views = Object.fromEntries(Object.entries(found?.views ?? {}).map(([view, entry]) => [view, entry.peak]));
    return { measured: { worst: value, view: found?.view ?? null, shift: found?.shift ?? null, views, ...failed(found?.failure, "the views were not measured") }, checks: rangeChecks(value, limits) };
  }
  if (name === "instanceRepetition") {
    const found = natural?.instanceRepetition;
    const value = found?.share ?? null;
    return {
      measured: { share: value, largestGroup: found?.largestGroup ?? 0, pieces: found?.pieces ?? 0, meshes: found?.meshes ?? 0, group: found?.group ?? null, ...failed(found?.failure, "the instances were not measured") },
      checks: rangeChecks(value, limits),
    };
  }
  if (name === "leonardo") {
    const found = natural?.leonardo;
    const value = found?.median ?? null;
    return {
      measured: { median: value, p25: found?.p25 ?? null, p75: found?.p75 ?? null, measured: found?.measured ?? 0, above: found?.above ?? 0, unmeasured: found?.unmeasured ?? 0, branchings: found?.branchings ?? 0, ...failed(found?.failure, "the skeleton was not measured") },
      checks: rangeChecks(value, limits),
    };
  }
  const found = natural?.sizeDistribution;
  const value = found?.exponent ?? null;
  return {
    measured: { exponent: value, xMin: found?.xMin ?? null, xMax: found?.xMax ?? null, tail: found?.tail ?? 0, count: found?.count ?? 0, ks: found?.ks ?? null, by: found?.by ?? null, ...failed(found?.failure, "the sizes were not measured") },
    checks: rangeChecks(value, limits),
  };
}

function shown(value: number | null | undefined): string {
  return value === null || value === undefined ? "none" : String(value);
}

export function setLines(natural: NaturalMeasurements): string[] {
  const parts: string[] = [];
  const { repetition, instanceRepetition, leonardo, sizeDistribution } = natural;
  if (repetition) parts.push(`repetition ${repetition.failure ?? `worst ${shown(repetition.worst)} in ${repetition.view} at shift ${repetition.shift?.join(",") ?? "none"}`}`);
  if (instanceRepetition) parts.push(`instance repetition ${instanceRepetition.failure ?? `${shown(instanceRepetition.share)} (${instanceRepetition.largestGroup} of ${instanceRepetition.pieces} pieces alike)`}`);
  if (leonardo) parts.push(`Leonardo ${leonardo.failure ?? `median delta ${shown(leonardo.median)} over ${leonardo.measured} branchings`}`);
  if (sizeDistribution) parts.push(`size exponent ${sizeDistribution.failure ?? `${shown(sizeDistribution.exponent)} above ${shown(sizeDistribution.xMin)} m over ${sizeDistribution.tail} of ${sizeDistribution.count} ${sizeDistribution.by} sizes`}`);
  return parts;
}
