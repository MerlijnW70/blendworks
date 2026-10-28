import { z } from "zod";

const finite = z.number().finite();
const count = z.number().int().nonnegative();

const roughnessObject = z.object({
  object: z.string().max(200),
  faces: count,
  samples: count,
  radius: finite.nullable(),
  p50: finite.nullable(),
  p90: finite.nullable(),
  flatShare: finite.nullable(),
});

export const surfaceRoughnessSchema = z.object({
  samplesPerObject: count,
  radiusDivisor: finite,
  flatDegrees: finite,
  objects: count,
  lowestP90: finite.nullable(),
  highestFlatShare: finite.nullable(),
  items: z.array(roughnessObject).max(64),
});

export const albedoVariationSchema = z.object({
  cv: finite.nullable(),
  texels: count,
  mean: finite.nullable(),
  images: z.array(z.object({ image: z.string().max(200), size: z.tuple([count, count]).nullable(), texels: count, mean: finite.nullable(), cv: finite.nullable() })).max(64),
  untexturedShare: finite.nullable(),
});

const silhouetteView = z.object({ dimension: finite.nullable(), boxCounts: z.array(finite), edgePixels: count, solidity: finite.nullable(), area: count, hullArea: finite, sha256: z.string() });

export const naturalSilhouettesSchema = z.object({
  size: count,
  views: z.record(z.string(), silhouetteView),
  dimension: finite.nullable(),
  solidity: finite.nullable(),
  failure: z.string().max(2000).nullable(),
});

const failure = z.string().max(2000).nullable();
const text = z.string().max(200);

export const instanceRepetitionSchema = z.object({
  objects: text,
  scaleTolerance: finite,
  yawToleranceDegrees: finite,
  pieces: count,
  meshes: count,
  share: finite.nullable(),
  largestGroup: count,
  group: z.object({ mesh: text, scale: finite, yaw: finite }).nullable(),
  failure,
});

const sizeBy = z.enum(["sphere", "trunk"]);

export const sizeSamplesSchema = z.object({ by: sizeBy, objects: text, sizes: z.array(finite).max(200_000), unmeasured: count, failure });

export const sizeDistributionSchema = z.object({
  by: sizeBy,
  objects: text,
  count,
  unmeasured: count,
  exponent: finite.nullable(),
  xMin: finite.nullable(),
  xMax: finite.nullable(),
  tail: count,
  ks: finite.nullable(),
  failure,
});

const skeletonRadii = z.object({ object: text, nodes: count, exponent: finite.nullable(), branchings: count, sampled: count, unmeasured: count, radii: z.array(z.array(finite).min(1).max(4096)).max(4096) });

export const skeletonSamplesSchema = z.object({ skeletons: z.array(skeletonRadii).max(64), refused: z.array(z.string().max(2000)).max(64), failure });

export const leonardoSchema = z.object({
  median: finite.nullable(),
  p25: finite.nullable(),
  p75: finite.nullable(),
  branchings: count,
  measured: count,
  solved: count,
  above: count,
  unmeasured: count,
  ceiling: finite,
  skeletons: z.array(z.object({ object: text, nodes: count, exponent: finite.nullable(), branchings: count, sampled: count, measured: count, unmeasured: count, median: finite.nullable() })).max(64),
  deltas: z.array(finite).max(64),
  refused: z.array(z.string().max(2000)).max(64),
  failure,
});

const repetitionView = z.object({ peak: finite.nullable(), shift: z.tuple([z.number().int(), z.number().int()]).nullable(), size: z.tuple([count, count]) });

export const repetitionSchema = z.object({
  minShift: count,
  minOverlap: finite,
  window: count,
  minEnergy: finite,
  worst: finite.nullable(),
  view: z.string().max(40).nullable(),
  shift: z.tuple([z.number().int(), z.number().int()]).nullable(),
  views: z.record(z.string(), repetitionView),
  failure,
});

export const scriptNaturalSchema = z.object({
  surfaceRoughness: surfaceRoughnessSchema.optional(),
  albedoVariation: albedoVariationSchema.optional(),
  instances: instanceRepetitionSchema.optional(),
  sizeSamples: sizeSamplesSchema.optional(),
  skeletons: skeletonSamplesSchema.optional(),
});

export const naturalMeasurementsSchema = z.object({
  surfaceRoughness: surfaceRoughnessSchema.optional(),
  albedoVariation: albedoVariationSchema.optional(),
  silhouettes: naturalSilhouettesSchema.optional(),
  instanceRepetition: instanceRepetitionSchema.optional(),
  sizeDistribution: sizeDistributionSchema.optional(),
  leonardo: leonardoSchema.optional(),
  repetition: repetitionSchema.optional(),
});

export type ScriptNatural = z.infer<typeof scriptNaturalSchema>;
export type NaturalMeasurements = z.infer<typeof naturalMeasurementsSchema>;
export type NaturalSilhouettes = z.infer<typeof naturalSilhouettesSchema>;
export type NaturalRepetition = z.infer<typeof repetitionSchema>;
