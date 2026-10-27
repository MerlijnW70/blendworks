import type { RuleResult } from "../judge/shape-rules.js";
import type { AssetSpec } from "../judge/spec.js";
import type { PackageReport } from "./report.js";

export const REACH_TOLERANCE = 1.05;
export const SCREEN_ERROR_SLACK = 1.0001;

export function wantsPackage(spec: AssetSpec): boolean {
  return spec.lods !== undefined || spec.package !== undefined;
}

function levels(report: PackageReport) {
  return report.levels.filter((level) => level.level > 0);
}

function validatorErrors(report: PackageReport): number {
  return report.files.reduce((sum, file) => sum + file.uncompressed.validation.errors + file.compressed.validation.errors, 0);
}

function equivalenceResult(report: PackageReport): RuleResult {
  const failed = [
    ...report.files.flatMap((file) => file.compressed.equivalence.checks.filter((check) => !check.pass).map((check) => `${file.compressed.path} ${check.name}`)),
    ...(report.roundTrip ?? []).filter((check) => !check.pass).map((check) => check.name),
  ];
  if (report.roundTrip === null) failed.push("blenderImport not run");
  return { rule: "package.equivalent", measured: failed.length === 0 ? "equivalent" : failed.join(", "), limit: "equivalent", pass: failed.length === 0 };
}

function worstOf(values: (number | null)[]): number | null {
  if (values.length === 0 || values.some((value) => value === null)) return null;
  return Math.min(...(values as number[]));
}

function lodRules(spec: AssetSpec, report: PackageReport): RuleResult[] {
  const lods = spec.lods;
  if (lods === undefined) return [];
  const built = levels(report);
  const results: RuleResult[] = [{ rule: "lods.count", measured: built.length, limit: lods.count, pass: built.length === lods.count }];
  if (lods.ratios !== undefined) {
    const targets = lods.ratios;
    const achieved = built.map((level) => Number(level.ratio.toFixed(4)));
    const pass = built.length === targets.length && built.every((level, index) => level.ratio <= (targets[index] ?? 0) * REACH_TOLERANCE);
    results.push({ rule: "lods.ratios", measured: achieved, limit: targets, pass });
  }
  if (lods.maxScreenError !== undefined) {
    const worst = built.length === 0 ? null : Math.max(...built.map((level) => level.screenErrorPixels ?? Infinity));
    const pass = worst !== null && worst <= lods.maxScreenError * SCREEN_ERROR_SLACK;
    results.push({ rule: "lods.maxScreenError", measured: worst === null || !Number.isFinite(worst) ? null : Number(worst.toFixed(4)), limit: lods.maxScreenError, pass });
  }
  if (lods.minSilhouetteIoU !== undefined) {
    const worst = worstOf(built.map((level) => level.render?.silhouetteIou ?? null));
    results.push({ rule: "lods.minSilhouetteIoU", measured: worst === null ? null : Number(worst.toFixed(4)), limit: lods.minSilhouetteIoU, pass: worst !== null && worst >= lods.minSilhouetteIoU });
  }
  if (lods.minSimilarity !== undefined) {
    const worst = worstOf(built.map((level) => level.render?.similarity ?? null));
    results.push({ rule: "lods.minSimilarity", measured: worst === null ? null : Number(worst.toFixed(4)), limit: lods.minSimilarity, pass: worst !== null && worst >= lods.minSimilarity });
  }
  return results;
}

function packageRules(spec: AssetSpec, report: PackageReport): RuleResult[] {
  const rule = spec.package;
  const errors = validatorErrors(report);
  const results: RuleResult[] = [
    { rule: "package.validator", measured: errors, limit: 0, pass: errors === 0 && report.files.length > 0 },
    equivalenceResult(report),
  ];
  if (rule?.compressedMaxBytes !== undefined) {
    results.push({ rule: "package.compressedMaxBytes", measured: report.sizes.compressedBytes, limit: rule.compressedMaxBytes, pass: report.sizes.compressedBytes <= rule.compressedMaxBytes });
  }
  if (rule?.ktx2 === true) {
    const { status, reason } = report.compression.ktx2;
    results.push({ rule: "package.ktx2", measured: reason === null ? status : `${status}: ${reason}`, limit: "written", pass: status === "written" || status === "no textures" });
  }
  if (rule?.meshopt !== undefined) {
    const used = report.files.length > 0 && report.files.every((file) => file.compressed.extensionsUsed.includes("EXT_meshopt_compression"));
    results.push({ rule: "package.meshopt", measured: used, limit: rule.meshopt, pass: used === rule.meshopt });
  }
  return results;
}

export function packageResults(spec: AssetSpec, report: PackageReport): RuleResult[] {
  return [...lodRules(spec, report), ...packageRules(spec, report)];
}
