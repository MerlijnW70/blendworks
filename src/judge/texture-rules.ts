import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./rules.js";
import { DEFAULT_FLOATING_TOLERANCE, type AssetSpec } from "./spec.js";
import type { Validation } from "./validator.js";

type Textures = NonNullable<Measurements["textures"]>;

function atMost(results: RuleResult[], rule: string, measured: number | null, limit: number | undefined): void {
  if (limit === undefined) return;
  results.push({ rule, measured, limit, pass: measured !== null && measured <= limit });
}

function requiredRule(required: readonly (keyof Textures["missing"])[], textures: Textures | undefined): RuleResult {
  if (textures === undefined) return { rule: "textures.required", measured: null, limit: required, pass: false };
  const missing = required.flatMap((kind) => {
    const { count, names } = textures.missing[kind];
    if (count === 0) return [];
    const more = count > names.length ? ` and ${count - names.length} more` : "";
    return [`${kind}: ${names.join(", ")}${more}`];
  });
  return { rule: "textures.required", measured: { materials: textures.materials.length, missing }, limit: required, pass: missing.length === 0 };
}

function listedRule(rule: string, key: string, list: { count: number; names: string[] } | undefined): RuleResult {
  if (list === undefined) return { rule, measured: null, limit: { [key]: 0 }, pass: false };
  return { rule, measured: { [key]: list.count, images: list.names }, limit: { [key]: 0 }, pass: list.count === 0 };
}

export function textureRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const rules = spec.textures;
  if (rules === undefined) return [];
  const textures = measurements.textures;
  const results: RuleResult[] = [];
  if (rules.required !== undefined) results.push(requiredRule(rules.required, textures));
  if (rules.minSize !== undefined) {
    const measured = textures === undefined ? null : textures.smallestSide;
    const pass = textures !== undefined && (measured === null || measured >= rules.minSize);
    results.push({ rule: "textures.minSize", measured, limit: rules.minSize, pass });
  }
  if (rules.maxSize !== undefined) {
    const measured = textures === undefined ? null : textures.largestSide;
    const pass = textures !== undefined && (measured === null || measured <= rules.maxSize);
    results.push({ rule: "textures.maxSize", measured, limit: rules.maxSize, pass });
  }
  if (rules.embedded === true) results.push(listedRule("textures.embedded", "external", textures?.external));
  atMost(results, "textures.maxCount", textures?.count ?? null, rules.maxCount);
  atMost(results, "textures.maxGpuBytes", textures?.gpuBytes ?? null, rules.maxGpuBytes);
  if (rules.powerOfTwo === true) results.push(listedRule("textures.powerOfTwo", "nonPowerOfTwo", textures?.nonPowerOfTwo));
  return results;
}

export function validatorRules(spec: AssetSpec, validation: Validation | null): RuleResult[] {
  const rule = spec.gltf?.validator;
  if (rule === undefined) return [];
  const results: RuleResult[] = [];
  atMost(results, "gltf.validator.maxErrors", validation?.errors ?? null, rule.maxErrors ?? 0);
  atMost(results, "gltf.validator.maxWarnings", validation?.warnings ?? null, rule.maxWarnings);
  return results;
}

export function floatingTolerance(spec: AssetSpec): number | undefined {
  if (spec.parts === undefined) return undefined;
  return spec.parts.tolerance ?? DEFAULT_FLOATING_TOLERANCE;
}

export function partsRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  if (spec.parts === undefined) return [];
  const floating = measurements.floating;
  const limit = spec.parts.maxFloating;
  if (floating === undefined) return [{ rule: "parts.maxFloating", measured: null, limit, pass: false }];
  const listed = floating.items.map((item) => `${item.object} part ${item.index}`);
  const more = floating.count > listed.length ? [`and ${floating.count - listed.length} more`] : [];
  return [
    {
      rule: "parts.maxFloating",
      measured: { floating: floating.count, parts: [...listed, ...more], tolerance: floating.tolerance },
      limit,
      pass: floating.count <= limit,
    },
  ];
}
