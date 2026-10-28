import type { NaturalLimits } from "./natural-spec.js";

export type CitedLimits = { limits: NaturalLimits; cites: string };

const INSTANCE_REPETITION: CitedLimits = { limits: { max: 0.1 }, cites: "docs/research/natural-shapes.md section 5: starting value 0.1, a design choice there, not verified" };
const LEONARDO: CitedLimits = { limits: { min: 1.8, max: 2.3 }, cites: "Eloy 2011 [S53]: 1.8 < Δ < 2.3 for a large number of species" };

export const NATURAL_CITED = {
  rock: { instanceRepetition: INSTANCE_REPETITION },
  tree: { instanceRepetition: INSTANCE_REPETITION, leonardo: LEONARDO },
  plant: { instanceRepetition: INSTANCE_REPETITION },
} as const;
