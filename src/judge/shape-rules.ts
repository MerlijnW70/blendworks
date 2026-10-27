import type { AssetSpec, OriginRule, SizeRule } from "./spec.js";

export type RuleResult = { rule: string; measured: unknown; limit: unknown; pass: boolean };

export type Vector = readonly [number, number, number] | readonly number[];

export type Placement = { size: Vector; point: Vector; bottomCentreDistance: number; centreDistance: number };

export const ORIGIN_TOLERANCE_RATIO = 0.01;
export const ORIGIN_TOLERANCE_FLOOR = 0.001;
const AXES = ["x", "y", "z"] as const;
const BLENDER_AXIS: Record<"z" | "y", Record<(typeof AXES)[number], number>> = { z: { x: 0, y: 1, z: 2 }, y: { x: 0, y: 2, z: 1 } };

export function upAxis(spec: AssetSpec): "z" | "y" {
  return spec.upAxis ?? "z";
}

export function toBlender(point: Vector, axis: "z" | "y"): [number, number, number] {
  const [x = 0, y = 0, z = 0] = point;
  return axis === "y" ? [x, -z, y] : [x, y, z];
}

export function originTolerance(size: Vector): number {
  return Math.max(ORIGIN_TOLERANCE_FLOOR, ORIGIN_TOLERANCE_RATIO * Math.max(...size));
}

function rounded(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

export function sizeRules(prefix: string, rule: SizeRule | undefined, size: Vector, axis: "z" | "y"): RuleResult[] {
  if (rule === undefined) return [];
  const results: RuleResult[] = [];
  for (const name of AXES) {
    const range = rule[name];
    if (range === undefined) continue;
    const measured = size[BLENDER_AXIS[axis][name]] ?? Number.NaN;
    results.push({ rule: `${prefix}size.${name}`, measured, limit: range, pass: measured >= range[0] && measured <= range[1] });
  }
  const extent = Math.max(...size);
  if (rule.minExtent !== undefined) results.push({ rule: `${prefix}size.minExtent`, measured: extent, limit: rule.minExtent, pass: extent >= rule.minExtent });
  if (rule.maxExtent !== undefined) results.push({ rule: `${prefix}size.maxExtent`, measured: extent, limit: rule.maxExtent, pass: extent <= rule.maxExtent });
  return results;
}

function distance(first: Vector, second: Vector): number {
  return Math.hypot(...[0, 1, 2].map((axis) => (first[axis] ?? 0) - (second[axis] ?? 0)));
}

export function originResult(rule: string, wanted: OriginRule, placement: Placement, axis: "z" | "y", extra: Record<string, unknown> = {}): RuleResult {
  if (typeof wanted !== "string") {
    const target = toBlender(wanted.point, axis);
    const away = rounded(distance(placement.point, target));
    return {
      rule,
      measured: { at: placement.point, ...extra, distanceFromRequired: away },
      limit: { at: wanted.point, tolerance: wanted.tolerance },
      pass: away <= wanted.tolerance,
    };
  }
  const tolerance = rounded(originTolerance(placement.size));
  const away = wanted === "bottom-centre" ? placement.bottomCentreDistance : placement.centreDistance;
  const nearest = placement.bottomCentreDistance <= tolerance ? "bottom-centre" : placement.centreDistance <= tolerance ? "centre" : "elsewhere";
  return {
    rule,
    measured: { at: nearest, point: placement.point, ...extra, distanceFromRequired: away },
    limit: { at: wanted, tolerance },
    pass: away <= tolerance,
  };
}

export function bounded(results: RuleResult[], name: string, measured: number, bounds: { min?: number | undefined; max?: number | undefined } | undefined): void {
  if (bounds?.min !== undefined) results.push({ rule: `${name}.min`, measured, limit: bounds.min, pass: measured >= bounds.min });
  if (bounds?.max !== undefined) results.push({ rule: `${name}.max`, measured, limit: bounds.max, pass: measured <= bounds.max });
}
