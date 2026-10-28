import { NATURAL_CLASSES, type NaturalClass, type NaturalLimitName, type NaturalRuleName } from "../../src/judge/natural-spec.js";

export const RESOLUTION = "1k";
export const PERCENTILES = [5, 25, 50, 75, 95] as const;
export const MIN_PER_CLASS = 8;
export const MIN_COVERAGE = 0.9;

export const SCANS: readonly { id: string; class: NaturalClass }[] = [
  { id: "rock_09", class: "rock" },
  { id: "coast_rocks_01", class: "rock" },
  { id: "coast_rocks_05", class: "rock" },
  { id: "moon_rock_01", class: "rock" },
  { id: "moon_rock_03", class: "rock" },
  { id: "namaqualand_boulder_02", class: "rock" },
  { id: "namaqualand_boulder_03", class: "rock" },
  { id: "namaqualand_boulder_04", class: "rock" },
  { id: "namaqualand_boulder_05", class: "rock" },
  { id: "namaqualand_boulder_06", class: "rock" },
  { id: "rock_moss_set_01", class: "rock" },
  { id: "stone_01", class: "rock" },
  { id: "dead_quiver_trunk", class: "tree" },
  { id: "dead_tree_trunk", class: "tree" },
  { id: "dead_tree_trunk_02", class: "tree" },
  { id: "dry_branches_medium_01", class: "tree" },
  { id: "fir_sapling", class: "tree" },
  { id: "othonna_cerarioides", class: "tree" },
  { id: "pine_sapling_small", class: "tree" },
  { id: "quiver_tree_01", class: "tree" },
  { id: "quiver_tree_02", class: "tree" },
  { id: "tree_stump_01", class: "tree" },
  { id: "tree_stump_02", class: "tree" },
  { id: "didelta_spinosa", class: "plant" },
  { id: "fern_02", class: "plant" },
  { id: "leipoldtia_schultzei", class: "plant" },
  { id: "nettle_plant", class: "plant" },
  { id: "periwinkle_plant", class: "plant" },
  { id: "searsia_lucida", class: "plant" },
  { id: "shrub_01", class: "plant" },
  { id: "shrub_02", class: "plant" },
  { id: "shrub_03", class: "plant" },
  { id: "shrub_04", class: "plant" },
  { id: "weed_plant_02", class: "plant" },
  { id: "wild_rooibos_bush", class: "plant" },
];

export type StandIn = { id: string; set: string; classes: readonly NaturalClass[]; measures: readonly string[]; description: string };

const SHAPE_MEASURES = ["dimension", "solidity", "p90", "flatShare", "albedoCv"];
const EVERY_CLASS = ["rock", "tree", "plant"] as const;

export const STAND_INS: readonly StandIn[] = [
  { id: "uv-sphere", set: "natural_fixtures", classes: ["rock"], measures: SHAPE_MEASURES, description: "UV sphere, 128 x 64 segments, with a single-colour texture" },
  { id: "clouds-ico", set: "natural_fixtures", classes: ["rock"], measures: SHAPE_MEASURES, description: "ico sphere (5 subdivisions) displaced by Clouds (size 0.4, strength 0.25), scaled (1, 0.8, 0.6)" },
  { id: "jittered-ico", set: "natural_fixtures", classes: ["rock"], measures: SHAPE_MEASURES, description: "ico sphere (1 subdivision), vertices jittered by up to 15 %, scaled (1, 0.75, 0.55)" },
  { id: "cylinder-tree", set: "natural_fixtures", classes: ["tree", "plant"], measures: SHAPE_MEASURES, description: "three-level tree of 40 tapered cylinders" },
  { id: "tiled-plane", set: "natural_sets_fixtures", classes: EVERY_CLASS, measures: ["repetition"], description: "2 m plane with a value-noise texture tiled 4 x 4" },
  { id: "copies-identical", set: "natural_sets_fixtures", classes: EVERY_CLASS, measures: ["repetition"], description: "100 copies of one pebble in a 10 x 10 grid, same scale and rotation" },
  { id: "sizes-uniform", set: "natural_sets_fixtures", classes: EVERY_CLASS, measures: ["sizeExponentLow", "sizeExponentHigh"], description: "300 stones with diameters drawn uniformly from 0.1 to 1 m" },
];

export type Direction = "min" | "max";

export type Measure = { key: string; rule: NaturalRuleName; limit: NaturalLimitName; direction: Direction; digits: number; label: string };

export const MEASURES: readonly Measure[] = [
  { key: "dimension", rule: "silhouetteDimension", limit: "min", direction: "min", digits: 2, label: "box-counting D (lowest of front, right)" },
  { key: "solidity", rule: "solidity", limit: "max", direction: "max", digits: 3, label: "solidity (lowest of front, right, top)" },
  { key: "p90", rule: "surfaceRoughness", limit: "p90Min", direction: "min", digits: 1, label: "normal deviation p90, degrees (lowest object)" },
  { key: "flatShare", rule: "surfaceRoughness", limit: "flatShareMax", direction: "max", digits: 3, label: "flat share under 3 degrees (highest object)" },
  { key: "albedoCv", rule: "albedoVariation", limit: "min", direction: "min", digits: 3, label: "albedo luminance CV" },
  { key: "repetition", rule: "repetition", limit: "max", direction: "max", digits: 3, label: "repetition peak (worst of front, right, top, three-quarter)" },
  { key: "sizeExponentLow", rule: "sizeDistribution", limit: "min", direction: "min", digits: 2, label: "size exponent of the pieces (lower limit)" },
  { key: "sizeExponentHigh", rule: "sizeDistribution", limit: "max", direction: "max", digits: 2, label: "size exponent of the pieces (upper limit)" },
];

export type Values = Record<string, number | null>;

export type MeasuredAsset = { id: string; kind: "scan" | "stand-in" | "procedural"; classes: NaturalClass[]; values: Values; measures?: string[] };

export function standsInFor(asset: MeasuredAsset, measure: string): boolean {
  return asset.measures === undefined || asset.measures.includes(measure);
}

export function percentile(values: readonly number[], p: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return Number.NaN;
  const position = ((sorted.length - 1) * p) / 100;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low]! + (sorted[high]! - sorted[low]!) * (position - low);
}

function roundTo(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export type Threshold = {
  measure: string;
  class: NaturalClass;
  direction: Direction;
  scans: number;
  realP5: number | null;
  realRange: [number, number] | null;
  worstStandIn: number | null;
  standIns: number;
  standInsMeasured: number;
  threshold: number | null;
  separates: boolean;
  realPassShare: number | null;
  standInFailShare: number | null;
  rule: string;
};

function passes(value: number | null, threshold: number, direction: Direction): boolean {
  return value !== null && (direction === "min" ? value >= threshold : value <= threshold);
}

export function deriveThreshold(measure: Measure, kind: NaturalClass, real: (number | null)[], standIns: (number | null)[]): Threshold {
  const measured = real.filter((value): value is number => value !== null);
  const values = standIns.filter((value): value is number => value !== null);
  const base = { measure: measure.key, class: kind, direction: measure.direction, scans: real.length, standIns: standIns.length, standInsMeasured: values.length };
  if (measured.length === 0) {
    return { ...base, realP5: null, realRange: null, worstStandIn: null, threshold: null, separates: false, realPassShare: null, standInFailShare: null, rule: "no scan of the class has this measurement" };
  }
  const tail = percentile(measured, measure.direction === "min" ? 5 : 95);
  const worst = values.length === 0 ? null : measure.direction === "min" ? Math.max(...values) : Math.min(...values);
  const step = 10 ** -measure.digits;
  const apart = worst !== null && (measure.direction === "min" ? tail - worst >= step : worst - tail >= step);
  let threshold = tail;
  let rule = measure.direction === "min" ? "5th percentile of the scans" : "95th percentile of the scans";
  if (apart && worst !== null) {
    const midpoint = (tail + worst) / 2;
    const rounded = roundTo(midpoint, measure.digits);
    const between = measure.direction === "min" ? rounded > worst && rounded <= tail : rounded < worst && rounded >= tail;
    threshold = between ? rounded : roundTo(midpoint, 6);
    rule = `midpoint between the ${measure.direction === "min" ? "5th" : "95th"} percentile of the scans and the worst stand-in`;
  } else threshold = roundTo(tail, 6);
  const realPassShare = real.filter((value) => passes(value, threshold, measure.direction)).length / real.length;
  const standInFailShare = standIns.length === 0 ? null : standIns.filter((value) => !passes(value, threshold, measure.direction)).length / standIns.length;
  return {
    ...base,
    realP5: roundTo(tail, 6),
    realRange: [roundTo(Math.min(...measured), 6), roundTo(Math.max(...measured), 6)],
    worstStandIn: worst === null ? null : roundTo(worst, 6),
    threshold,
    separates: apart && standInFailShare === 1 && measured.length >= MIN_COVERAGE * real.length,
    realPassShare: roundTo(realPassShare, 4),
    standInFailShare: standInFailShare === null ? null : roundTo(standInFailShare, 4),
    rule,
  };
}

export type ClassPercentiles = Record<string, { n: number; values: Record<string, number> | null }>;

export function classPercentiles(assets: readonly MeasuredAsset[], kind: NaturalClass): ClassPercentiles {
  const scans = assets.filter((asset) => asset.kind === "scan" && asset.classes.includes(kind));
  return Object.fromEntries(
    MEASURES.map((measure) => {
      const values = scans.map((asset) => asset.values[measure.key]).filter((value): value is number => value !== null && value !== undefined);
      return [measure.key, { n: values.length, values: values.length === 0 ? null : Object.fromEntries(PERCENTILES.map((p) => [`p${p}`, roundTo(percentile(values, p), 6)])) }];
    }),
  );
}

export function thresholds(assets: readonly MeasuredAsset[]): Threshold[] {
  const found: Threshold[] = [];
  for (const kind of NATURAL_CLASSES) {
    const scans = assets.filter((asset) => asset.kind === "scan" && asset.classes.includes(kind));
    const standIns = assets.filter((asset) => asset.kind === "stand-in" && asset.classes.includes(kind));
    for (const measure of MEASURES) {
      found.push(
        deriveThreshold(
          measure,
          kind,
          scans.map((asset) => asset.values[measure.key] ?? null),
          standIns.filter((asset) => standsInFor(asset, measure.key)).map((asset) => asset.values[measure.key] ?? null),
        ),
      );
    }
  }
  return found;
}

export type Defaults = Record<NaturalClass, Partial<Record<NaturalRuleName, Partial<Record<NaturalLimitName, number>>>>>;

export function defaultsFrom(found: readonly Threshold[]): Defaults {
  const defaults = Object.fromEntries(NATURAL_CLASSES.map((kind) => [kind, {}])) as Defaults;
  for (const entry of found) {
    if (!entry.separates || entry.threshold === null) continue;
    const measure = MEASURES.find((candidate) => candidate.key === entry.measure)!;
    const limits = (defaults[entry.class][measure.rule] ??= {});
    limits[measure.limit] = entry.threshold;
  }
  return defaults;
}

export function defaultsSource(defaults: Defaults): string {
  const classes = NATURAL_CLASSES.map((kind) => {
    const rules = Object.entries(defaults[kind]).map(([rule, limits]) => `${rule}: { ${Object.entries(limits ?? {}).map(([name, value]) => `${name}: ${value}`).join(", ")} }`);
    return `  ${kind}: {${rules.length === 0 ? "" : ` ${rules.join(", ")} `}},`;
  });
  return ['export const NATURAL_CALIBRATION = "docs/research/natural-shapes/calibration.json";', "", "export const NATURAL_DEFAULTS = {", ...classes, "} as const;", ""].join("\n");
}

export type ProceduralScore = { id: string; class: NaturalClass; limits: { limit: string; threshold: number; value: number | null; pass: boolean }[]; passes: boolean };

export function proceduralScores(assets: readonly MeasuredAsset[], defaults: Defaults): ProceduralScore[] {
  return assets
    .filter((asset) => asset.kind === "procedural")
    .flatMap((asset) =>
      asset.classes.map((kind) => {
        const limits = MEASURES.flatMap((measure) => {
          const threshold = defaults[kind][measure.rule]?.[measure.limit];
          if (threshold === undefined) return [];
          const value = asset.values[measure.key] ?? null;
          return [{ limit: `natural.${measure.rule}.${measure.limit}`, threshold, value, pass: passes(value, threshold, measure.direction) }];
        });
        return { id: asset.id, class: kind, limits, passes: limits.length > 0 && limits.every((entry) => entry.pass) };
      }),
    );
}
