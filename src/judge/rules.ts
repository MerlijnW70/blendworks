import type { Measurements } from "./measurements.js";
import type { AssetSpec } from "./spec.js";

export type RuleResult = { rule: string; measured: unknown; limit: unknown; pass: boolean };

export const ORIGIN_TOLERANCE_RATIO = 0.01;
export const ORIGIN_TOLERANCE_FLOOR = 0.001;
const AXES = ["x", "y", "z"] as const;

type Bounds = { min?: number | undefined; max?: number | undefined } | undefined;

function bounded(results: RuleResult[], name: string, measured: number, bounds: Bounds): void {
  if (bounds?.min !== undefined) results.push({ rule: `${name}.min`, measured, limit: bounds.min, pass: measured >= bounds.min });
  if (bounds?.max !== undefined) results.push({ rule: `${name}.max`, measured, limit: bounds.max, pass: measured <= bounds.max });
}

export function originTolerance(size: readonly number[]): number {
  return Math.max(ORIGIN_TOLERANCE_FLOOR, ORIGIN_TOLERANCE_RATIO * Math.max(...size));
}

function originRule(spec: AssetSpec, measurements: Measurements): RuleResult | undefined {
  if (spec.origin === undefined) return undefined;
  const { origin, size } = measurements;
  const tolerance = Math.round(originTolerance(size) * 1e6) / 1e6;
  const distance = spec.origin === "bottom-centre" ? origin.bottomCentreDistance : origin.centreDistance;
  const nearest =
    origin.bottomCentreDistance <= tolerance ? "bottom-centre" : origin.centreDistance <= tolerance ? "centre" : "elsewhere";
  return {
    rule: "origin",
    measured: { at: nearest, point: origin.point, source: origin.source, distanceFromRequired: distance },
    limit: { at: spec.origin, tolerance },
    pass: distance <= tolerance,
  };
}

function manifoldRule(spec: AssetSpec, measurements: Measurements): RuleResult | undefined {
  if (spec.manifold !== true) return undefined;
  const { nonManifoldEdges, boundaryEdges, wireEdges, nonManifoldVertices, looseVertices, looseParts } = measurements.manifold;
  const defects = { nonManifoldEdges, boundaryEdges, wireEdges, nonManifoldVertices, looseVertices };
  return {
    rule: "manifold",
    measured: { ...defects, looseParts },
    limit: { nonManifoldEdges: 0, boundaryEdges: 0, wireEdges: 0, nonManifoldVertices: 0, looseVertices: 0 },
    pass: Object.values(defects).every((value) => value === 0),
  };
}

function uvRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const results: RuleResult[] = [];
  const { uv } = measurements;
  if (spec.uv?.required === true) results.push({ rule: "uv.required", measured: uv.present, limit: true, pass: uv.present });
  if (spec.uv?.maxOverlap !== undefined) {
    const measured = uv.present ? uv.overlap : null;
    results.push({ rule: "uv.maxOverlap", measured, limit: spec.uv.maxOverlap, pass: measured !== null && measured <= spec.uv.maxOverlap });
  }
  if (spec.uv?.minCoverage !== undefined) {
    const measured = uv.present ? uv.coverage : null;
    results.push({ rule: "uv.minCoverage", measured, limit: spec.uv.minCoverage, pass: measured !== null && measured >= spec.uv.minCoverage });
  }
  return results;
}

export function evaluateRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const results: RuleResult[] = [
    { rule: "format", measured: measurements.format, limit: spec.format, pass: measurements.format === spec.format },
  ];
  bounded(results, "triangles", measurements.triangles, spec.triangles);
  AXES.forEach((axis, index) => {
    const range = spec.size?.[axis];
    if (range === undefined) return;
    const measured = measurements.size[index] ?? Number.NaN;
    results.push({ rule: `size.${axis}`, measured, limit: range, pass: measured >= range[0] && measured <= range[1] });
  });
  const origin = originRule(spec, measurements);
  if (origin) results.push(origin);
  const manifold = manifoldRule(spec, measurements);
  if (manifold) results.push(manifold);
  bounded(results, "materials", measurements.materials.count, spec.materials);
  results.push(...uvRules(spec, measurements));
  bounded(results, "objects", measurements.objects, spec.objects);
  if (spec.fileSize !== undefined) {
    results.push({ rule: "fileSize.maxBytes", measured: measurements.fileBytes, limit: spec.fileSize.maxBytes, pass: measurements.fileBytes <= spec.fileSize.maxBytes });
  }
  return results;
}
