import { z } from "zod";
import { NATURAL_DEFAULTS } from "./natural-defaults.js";
import { ratio } from "./spec-shapes.js";

export const NATURAL_CLASSES = ["rock", "tree", "plant"] as const;
export type NaturalClass = (typeof NATURAL_CLASSES)[number];

export const NATURAL_RULES = ["silhouetteDimension", "solidity", "surfaceRoughness", "albedoVariation"] as const;
export type NaturalRuleName = (typeof NATURAL_RULES)[number];

export type NaturalLimitName = "min" | "max" | "p90Min" | "flatShareMax";
export type NaturalLimits = Partial<Record<NaturalLimitName, number>>;

const ordered = (value: { min?: number | undefined; max?: number | undefined }) => value.min === undefined || value.max === undefined || value.min <= value.max;
const minNotOverMax = { message: "min must not exceed max" };

const dimension = z.number().min(0).max(2);
const nonNegative = z.number().nonnegative().finite();

const silhouetteDimension = z.strictObject({ min: dimension.optional(), max: dimension.optional() }).refine(ordered, minNotOverMax);
const solidity = z.strictObject({ min: ratio.optional(), max: ratio.optional() }).refine(ordered, minNotOverMax);
const surfaceRoughness = z.strictObject({ p90Min: z.number().min(0).max(180).optional(), flatShareMax: ratio.optional() });
const albedoVariation = z.strictObject({ min: nonNegative.optional(), max: nonNegative.optional() }).refine(ordered, minNotOverMax);

export function calibratedLimits(kind: NaturalClass, rule: NaturalRuleName): NaturalLimits | undefined {
  const limits = (NATURAL_DEFAULTS as Record<NaturalClass, Partial<Record<NaturalRuleName, NaturalLimits>>>)[kind][rule];
  return limits === undefined || Object.keys(limits).length === 0 ? undefined : limits;
}

export const naturalRule = z
  .strictObject({
    class: z.enum(NATURAL_CLASSES),
    silhouetteDimension: silhouetteDimension.optional(),
    solidity: solidity.optional(),
    surfaceRoughness: surfaceRoughness.optional(),
    albedoVariation: albedoVariation.optional(),
  })
  .superRefine((value, context) => {
    const named = NATURAL_RULES.filter((rule) => value[rule] !== undefined);
    if (named.length === 0) context.addIssue({ code: "custom", message: `the natural group needs at least one of ${NATURAL_RULES.join(", ")}` });
    for (const rule of named) {
      if (Object.keys(value[rule] ?? {}).length > 0 || calibratedLimits(value.class, rule) !== undefined) continue;
      context.addIssue({
        code: "custom",
        path: [rule],
        message: `${rule} has no calibrated default for class ${value.class}, because the calibration does not separate ${value.class} scans from stand-ins on it; give its limits`,
      });
    }
  });

export type NaturalRule = z.infer<typeof naturalRule>;

export type ResolvedLimits = { limits: NaturalLimits; source: "spec" | "calibrated" };

export function naturalLimits(rule: NaturalRule, name: NaturalRuleName): ResolvedLimits | undefined {
  const given = rule[name];
  if (given === undefined) return undefined;
  if (Object.keys(given).length > 0) return { limits: given as NaturalLimits, source: "spec" };
  const calibrated = calibratedLimits(rule.class, name);
  return calibrated === undefined ? undefined : { limits: calibrated, source: "calibrated" };
}

export function wantsNaturalSilhouettes(rule: NaturalRule | undefined): boolean {
  return rule !== undefined && (rule.silhouetteDimension !== undefined || rule.solidity !== undefined);
}

export function naturalMeasureParts(rule: NaturalRule | undefined): string[] {
  if (rule === undefined) return [];
  return [...(rule.surfaceRoughness === undefined ? [] : ["roughness"]), ...(rule.albedoVariation === undefined ? [] : ["albedo"])];
}
