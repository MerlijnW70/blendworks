import { DELTA_CEILING, summarizeDeltas } from "./natural-leonardo.js";
import { fitPowerLaw } from "./natural-power.js";
import { REPETITION_MIN_ENERGY, REPETITION_MIN_OVERLAP, REPETITION_MIN_SHIFT, REPETITION_WINDOW, repetitionOf } from "./natural-repetition.js";
import type { NaturalMeasurements, NaturalRepetition, ScriptNatural } from "./natural-schema.js";
import { readShared } from "./shared-access.js";
import { decodePng, PngError } from "./visual/png.js";

const LISTED = 64;

type SizeSamples = NonNullable<ScriptNatural["sizeSamples"]>;
type SkeletonSamples = NonNullable<ScriptNatural["skeletons"]>;

export function sizeDistribution(samples: SizeSamples): NonNullable<NaturalMeasurements["sizeDistribution"]> {
  const base = { by: samples.by, objects: samples.objects, count: samples.sizes.length, unmeasured: samples.unmeasured };
  if (samples.failure !== null) return { ...base, exponent: null, xMin: null, xMax: null, tail: 0, ks: null, failure: samples.failure };
  const fit = fitPowerLaw(samples.sizes);
  return { ...base, ...fit };
}

export function leonardo(samples: SkeletonSamples): NonNullable<NaturalMeasurements["leonardo"]> {
  const pooled = samples.skeletons.flatMap((skeleton) => skeleton.radii);
  const summary = summarizeDeltas(pooled);
  const skeletons = samples.skeletons.map((skeleton) => ({
    object: skeleton.object,
    nodes: skeleton.nodes,
    exponent: skeleton.exponent,
    branchings: skeleton.branchings,
    sampled: skeleton.sampled,
    measured: skeleton.radii.length,
    unmeasured: skeleton.unmeasured,
    median: summarizeDeltas(skeleton.radii).median,
  }));
  const unmeasured = samples.skeletons.reduce((sum, skeleton) => sum + skeleton.unmeasured, 0) + summary.invalid;
  let failure = samples.failure;
  if (failure === null && summary.median === null) failure = "no branching of the skeleton could be measured on the mesh";
  return {
    median: failure === null ? summary.median : null,
    p25: summary.p25,
    p75: summary.p75,
    branchings: samples.skeletons.reduce((sum, skeleton) => sum + skeleton.branchings, 0),
    measured: summary.solved + summary.above,
    solved: summary.solved,
    above: summary.above,
    unmeasured,
    ceiling: DELTA_CEILING,
    skeletons,
    deltas: summary.deltas.slice(0, LISTED),
    refused: samples.refused,
    failure,
  };
}

export function finishNatural(script: ScriptNatural | undefined): NaturalMeasurements | undefined {
  if (script === undefined) return undefined;
  const { instances, sizeSamples, skeletons, ...rest } = script;
  return {
    ...rest,
    ...(instances === undefined ? {} : { instanceRepetition: instances }),
    ...(sizeSamples === undefined ? {} : { sizeDistribution: sizeDistribution(sizeSamples) }),
    ...(skeletons === undefined ? {} : { leonardo: leonardo(skeletons) }),
  };
}

export function naturalRepetition(views: readonly { view: string; path: string }[], reason: string | null): NaturalRepetition {
  const result: NaturalRepetition = {
    minShift: REPETITION_MIN_SHIFT,
    minOverlap: REPETITION_MIN_OVERLAP,
    window: REPETITION_WINDOW,
    minEnergy: REPETITION_MIN_ENERGY,
    worst: null,
    view: null,
    shift: null,
    views: {},
    failure: null,
  };
  if (views.length === 0) return { ...result, failure: reason ?? "the views did not render" };
  for (const entry of views) {
    let image;
    try {
      image = decodePng(readShared(entry.path));
    } catch (error) {
      if (error instanceof PngError || (error as NodeJS.ErrnoException).code === "ENOENT") return { ...result, views: {}, failure: `the ${entry.view} view cannot be read` };
      throw error;
    }
    const peak = repetitionOf(image);
    result.views[entry.view] = peak;
    if (peak.peak === null) continue;
    if (result.worst === null || peak.peak > result.worst) {
      result.worst = peak.peak;
      result.view = entry.view;
      result.shift = peak.shift;
    }
  }
  const missing = Object.entries(result.views).filter(([, entry]) => entry.peak === null);
  if (missing.length > 0) return { ...result, worst: null, view: null, shift: null, failure: `the ${missing.map(([view]) => view).join(", ")} view shows no detail to compare` };
  return result;
}
