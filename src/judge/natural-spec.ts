import { z } from "zod";
import { NATURAL_CITED, type CitedLimits } from "./natural-cited.js";
import { NATURAL_DEFAULTS } from "./natural-defaults.js";
import { ratio } from "./spec-shapes.js";

export const NATURAL_CLASSES = ["rock", "tree", "plant"] as const;
export type NaturalClass = (typeof NATURAL_CLASSES)[number];

export const NATURAL_RULES = ["silhouetteDimension", "solidity", "surfaceRoughness", "albedoVariation", "repetition", "instanceRepetition", "leonardo", "sizeDistribution"] as const;
export type NaturalRuleName = (typeof NATURAL_RULES)[number];

export type NaturalLimitName = "min" | "max" | "p90Min" | "flatShareMax";
export type NaturalLimits = Partial<Record<NaturalLimitName, number>>;
export const SIZE_MEASURES = ["sphere", "trunk"] as const;
export type SizeMeasure = (typeof SIZE_MEASURES)[number];
export type NaturalOptions = { objects?: string; by?: SizeMeasure };

const ordered = (value: { min?: number | undefined; max?: number | undefined }) => value.min === undefined || value.max === undefined || value.min <= value.max;
const minNotOverMax = { message: "min must not exceed max" };

const dimension = z.number().min(0).max(2);
const nonNegative = z.number().nonnegative().finite();
const pattern = z.string().min(1).max(200);
const delta = z.number().min(0).max(10);
const exponent = z.number().min(-12).max(8);

const silhouetteDimension = z.strictObject({ min: dimension.optional(), max: dimension.optional() }).refine(ordered, minNotOverMax);
const solidity = z.strictObject({ min: ratio.optional(), max: ratio.optional() }).refine(ordered, minNotOverMax);
const surfaceRoughness = z.strictObject({ p90Min: z.number().min(0).max(180).optional(), flatShareMax: ratio.optional() });
const albedoVariation = z.strictObject({ min: nonNegative.optional(), max: nonNegative.optional() }).refine(ordered, minNotOverMax);
const repetition = z.strictObject({ max: ratio.optional() });
const instanceRepetition = z.strictObject({ max: ratio.optional(), objects: pattern.optional() });
const leonardo = z.strictObject({ min: delta.optional(), max: delta.optional() }).refine(ordered, minNotOverMax);
const sizeDistribution = z.strictObject({ min: exponent.optional(), max: exponent.optional(), by: z.enum(SIZE_MEASURES).optional(), objects: pattern.optional() }).refine(ordered, minNotOverMax);

const LIMIT_NAMES: readonly string[] = ["min", "max", "p90Min", "flatShareMax"];

export function calibratedLimits(kind: NaturalClass, rule: NaturalRuleName): NaturalLimits | undefined {
  const limits = (NATURAL_DEFAULTS as Record<NaturalClass, Partial<Record<NaturalRuleName, NaturalLimits>>>)[kind][rule];
  return limits === undefined || Object.keys(limits).length === 0 ? undefined : limits;
}

export function citedLimits(kind: NaturalClass, rule: NaturalRuleName): CitedLimits | undefined {
  return (NATURAL_CITED as Record<NaturalClass, Partial<Record<NaturalRuleName, CitedLimits>>>)[kind][rule];
}

function givenLimits(given: Record<string, unknown>): NaturalLimits {
  return Object.fromEntries(Object.entries(given).filter(([key]) => LIMIT_NAMES.includes(key))) as NaturalLimits;
}

export const naturalRule = z
  .strictObject({
    class: z.enum(NATURAL_CLASSES),
    silhouetteDimension: silhouetteDimension.optional(),
    solidity: solidity.optional(),
    surfaceRoughness: surfaceRoughness.optional(),
    albedoVariation: albedoVariation.optional(),
    repetition: repetition.optional(),
    instanceRepetition: instanceRepetition.optional(),
    leonardo: leonardo.optional(),
    sizeDistribution: sizeDistribution.optional(),
  })
  .superRefine((value, context) => {
    const named = NATURAL_RULES.filter((rule) => value[rule] !== undefined);
    if (named.length === 0) context.addIssue({ code: "custom", message: `the natural group needs at least one of ${NATURAL_RULES.join(", ")}` });
    for (const rule of named) {
      if (Object.keys(givenLimits(value[rule] ?? {})).length > 0 || calibratedLimits(value.class, rule) !== undefined || citedLimits(value.class, rule) !== undefined) continue;
      context.addIssue({
        code: "custom",
        path: [rule],
        message: `${rule} has no calibrated default for class ${value.class}, because the calibration does not separate ${value.class} scans from stand-ins on it and no cited source sets one; give its limits`,
      });
    }
  });

export type NaturalRule = z.infer<typeof naturalRule>;

export type ResolvedLimits = { limits: NaturalLimits; options: NaturalOptions; source: "spec" | "calibrated" | "cited"; cites?: string };

function optionsOf(given: Record<string, unknown>): NaturalOptions {
  const options: NaturalOptions = {};
  if (typeof given["objects"] === "string") options.objects = given["objects"];
  if (given["by"] === "sphere" || given["by"] === "trunk") options.by = given["by"];
  return options;
}

export function naturalLimits(rule: NaturalRule, name: NaturalRuleName): ResolvedLimits | undefined {
  const given = rule[name] as Record<string, unknown> | undefined;
  if (given === undefined) return undefined;
  const options = optionsOf(given);
  const limits = givenLimits(given);
  if (Object.keys(limits).length > 0) return { limits, options, source: "spec" };
  const calibrated = calibratedLimits(rule.class, name);
  if (calibrated !== undefined) return { limits: calibrated, options, source: "calibrated" };
  const cited = citedLimits(rule.class, name);
  return cited === undefined ? undefined : { limits: cited.limits, options, source: "cited", cites: cited.cites };
}

export function wantsNaturalSilhouettes(rule: NaturalRule | undefined): boolean {
  return rule !== undefined && (rule.silhouetteDimension !== undefined || rule.solidity !== undefined);
}

export function sizeMeasure(rule: NaturalRule): SizeMeasure {
  return rule.sizeDistribution?.by ?? (rule.class === "tree" ? "trunk" : "sphere");
}

export function naturalMeasureParts(rule: NaturalRule | undefined): string[] {
  if (rule === undefined) return [];
  const parts: [string, unknown][] = [
    ["roughness", rule.surfaceRoughness],
    ["albedo", rule.albedoVariation],
    ["instances", rule.instanceRepetition],
    ["sizes", rule.sizeDistribution],
    ["leonardo", rule.leonardo],
  ];
  return parts.filter(([, wanted]) => wanted !== undefined).map(([part]) => part);
}

export function naturalMeasureOptions(rule: NaturalRule | undefined): string[] {
  if (rule === undefined) return [];
  return [
    ...(rule.instanceRepetition === undefined ? [] : ["--natural-instances", rule.instanceRepetition.objects ?? "*"]),
    ...(rule.sizeDistribution === undefined ? [] : ["--natural-sizes", `${sizeMeasure(rule)}:${rule.sizeDistribution.objects ?? "*"}`]),
  ];
}
