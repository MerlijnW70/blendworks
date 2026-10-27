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

export const scriptNaturalSchema = z.object({ surfaceRoughness: surfaceRoughnessSchema.optional(), albedoVariation: albedoVariationSchema.optional() });
export const naturalMeasurementsSchema = scriptNaturalSchema.extend({ silhouettes: naturalSilhouettesSchema.optional() });

export type NaturalMeasurements = z.infer<typeof naturalMeasurementsSchema>;
export type NaturalSilhouettes = z.infer<typeof naturalSilhouettesSchema>;
