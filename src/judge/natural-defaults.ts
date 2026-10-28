export const NATURAL_CALIBRATION = "docs/research/natural-shapes/calibration.json";

export const NATURAL_DEFAULTS = {
  rock: { solidity: { max: 0.976 }, surfaceRoughness: { p90Min: 14 }, albedoVariation: { min: 0.026 }, repetition: { max: 0.754 } },
  tree: { surfaceRoughness: { flatShareMax: 0.365 }, repetition: { max: 0.763 } },
  plant: { repetition: { max: 0.717 }, sizeDistribution: { max: -1.07 } },
} as const;
