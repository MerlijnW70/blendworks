import { manifoldRules, selfContainedRules, surfaceRules } from "./integrity-rules.js";
import type { Measurements } from "./measurements.js";
import { motionRules } from "./motion-rules.js";
import { objectRules } from "./object-rules.js";
import { bounded, originResult, sizeRules, upAxis, type RuleResult } from "./shape-rules.js";
import type { AssetSpec } from "./spec.js";
import { partsRules, textureRules, validatorRules } from "./texture-rules.js";
import type { Validation } from "./validator.js";

export type { RuleResult } from "./shape-rules.js";
export { ORIGIN_TOLERANCE_FLOOR, ORIGIN_TOLERANCE_RATIO, originTolerance } from "./shape-rules.js";

function uvRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const results: RuleResult[] = [];
  const { uv } = measurements;
  if (spec.uv?.required === true) results.push({ rule: "uv.required", measured: uv.present, limit: true, pass: uv.present });
  if (spec.uv?.maxOverlap !== undefined) {
    const measured = uv.present ? uv.overlap : null;
    results.push({ rule: "uv.maxOverlap", measured, limit: spec.uv.maxOverlap, pass: measured !== null && measured <= spec.uv.maxOverlap });
  }
  if (spec.uv?.minCoverage !== undefined) {
    const measured = uv.present ? uv.coverage : null;
    results.push({ rule: "uv.minCoverage", measured, limit: spec.uv.minCoverage, pass: measured !== null && measured >= spec.uv.minCoverage });
  }
  return results;
}

export function evaluateRules(spec: AssetSpec, measurements: Measurements, validation: Validation | null = null): RuleResult[] {
  const axis = upAxis(spec);
  const results: RuleResult[] = [{ rule: "format", measured: measurements.format, limit: spec.format, pass: measurements.format === spec.format }];
  bounded(results, "triangles", measurements.triangles, spec.triangles);
  results.push(...sizeRules("", spec.size, measurements.size, axis));
  if (spec.origin !== undefined) {
    const { origin, size } = measurements;
    results.push(originResult("origin", spec.origin, { size, ...origin }, axis, { source: origin.source }));
  }
  results.push(...manifoldRules(spec, measurements), ...surfaceRules(spec, measurements));
  bounded(results, "materials", measurements.materials.count, spec.materials);
  results.push(...uvRules(spec, measurements));
  bounded(results, "objects", measurements.objects, spec.objects);
  results.push(...objectRules(spec, measurements));
  if (spec.fileSize !== undefined) {
    results.push({ rule: "fileSize.maxBytes", measured: measurements.fileBytes, limit: spec.fileSize.maxBytes, pass: measurements.fileBytes <= spec.fileSize.maxBytes });
  }
  results.push(...selfContainedRules(spec, measurements));
  results.push(...textureRules(spec, measurements), ...partsRules(spec, measurements), ...validatorRules(spec, validation));
  results.push(...motionRules(spec, measurements));
  return results;
}
