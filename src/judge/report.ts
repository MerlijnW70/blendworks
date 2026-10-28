import { describeDevice, type RenderDevice } from "./device.js";
import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./rules.js";
import { containerText, type ContainerIsolation } from "./isolation.js";
import type { Isolation } from "./sandbox.js";
import type { Validation } from "./validator.js";
import { motionLines } from "./motion-summary.js";
import { naturalLines } from "./natural.js";
import { referenceLines, type ReferenceRecord } from "./reference.js";
import { visualLines, type VisualRecord } from "./visual/record.js";
import { packageLines, type PackageReport } from "../package/report.js";

export type Failure = { stage: "spec" | "asset" | "validate" | "blender" | "measure" | "reference" | "device" | "render" | "closeups" | "package"; code: string; message: string };

export type RenderedView = { view: string; path: string; sha256: string };

export type RenderBudget = { triangles: number; samplePixels: number; maxTriangles: number; maxSamplePixels: number };

export type Renders = {
  status: "rendered" | "preview" | "skipped" | "failed";
  reason: string | null;
  failure: Failure | null;
  viewsSkipped: boolean;
  views: RenderedView[];
  contactSheet: string | null;
  contactSheetSha256: string | null;
  budget: RenderBudget;
};

export type AssetRecord = {
  path: string;
  sha256: string | null;
  bytes: number | null;
  files: { path: string; bytes: number; sha256: string }[];
  setSha256: string | null;
  setBytes: number | null;
};

export const STAGES = ["measure", "reference", "device", "render", "sheet", "closeups"] as const;
const PASS_ONLY = ["reference", "closeups"] as const;

export type Timings = Record<Exclude<(typeof STAGES)[number], (typeof PASS_ONLY)[number]>, number | null> & Partial<Record<(typeof PASS_ONLY)[number], number | null>> & { total: number };

export type Report = {
  passed: boolean;
  preview: boolean;
  spec: { path: string; sha256: string | null; name: string | null };
  asset: AssetRecord;
  blender: string | null;
  sandbox: Isolation | null;
  renderSandbox: Isolation | null;
  container?: ContainerIsolation | null;
  device: RenderDevice | null;
  failure: Failure | null;
  rules: RuleResult[];
  measurements: Measurements | null;
  renders: Renders | null;
  timings: Timings;
  validation?: Validation | null;
  visual?: VisualRecord | null;
  package?: PackageReport | null;
  reference?: ReferenceRecord | null;
  summary: string;
};

const LISTED_ISSUES = 10;
const MEBIBYTE = 1024 * 1024;

function show(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `[${value.map(show).join(", ")}]`;
  if (value !== null && typeof value === "object" && "at" in value) {
    const { at, distanceFromRequired, tolerance } = value as { at: unknown; distanceFromRequired?: unknown; tolerance?: unknown };
    if (distanceFromRequired !== undefined) return `${show(at)}, ${show(distanceFromRequired)} m from the required point`;
    if (tolerance !== undefined) return `${show(at)} within ${show(tolerance)} m`;
  }
  if (value !== null && typeof value === "object") {
    return Object.entries(value)
      .map(([key, entry]) => `${key} ${show(entry)}`)
      .join(", ");
  }
  return String(value);
}

function comparison(rule: string): string {
  if (/\.min([A-Z]\w*)?$/.test(rule)) return "at least ";
  if (/\.max([A-Z]\w*)?$/.test(rule)) return "at most ";
  if (rule.startsWith("size.") || /^animation\.boundsWithin\.size\.[xyz]$/.test(rule)) return "between ";
  return "";
}

export function isolationText(isolation: Isolation): string {
  return `network ${isolation.network}; memory ${isolation.memory}; timeout ${isolation.timeoutMs / 1000} s; files ${isolation.filesystem}; processes ${isolation.processes}`;
}

function renderLines(renders: Renders): string[] {
  const lines: string[] = [];
  if (renders.status === "preview") lines.push("  views: skipped (preview); the rules alone decide pass or fail");
  if (renders.status === "skipped") lines.push(`  views: skipped (${renders.reason}); the rules alone decide pass or fail`);
  if (renders.status === "failed") lines.push(`  views: not rendered (${renders.failure?.stage ?? "render"} failed: ${renders.reason}); the rules alone decide pass or fail`);
  if (renders.contactSheet !== null) lines.push(`  contact sheet: ${renders.contactSheet}`);
  return lines;
}

export function timingText(timings: Timings): string {
  const stages = STAGES.flatMap((stage) => {
    const value = timings[stage];
    return value === null || value === undefined ? [] : [`${stage} ${value.toFixed(2)} s`];
  });
  return [...stages, `total ${timings.total.toFixed(2)} s`].join(", ");
}

function textureLines(textures: NonNullable<Measurements["textures"]>): string[] {
  const lines = [`  textures: ${textures.count} images, GPU estimate ${textures.gpuBytes} bytes (${(textures.gpuBytes / MEBIBYTE).toFixed(1)} MiB, RGBA8 with mips)`];
  const { count, items } = textures.colourSpaceMismatches;
  if (count === 0) return [...lines, "  colour spaces: right for every map"];
  lines.push(`  colour spaces: ${count} wrong`);
  for (const item of items) lines.push(`    ${item.image} as ${item.kind} is ${item.colourSpace}, expected ${item.expected}`);
  if (count > items.length) lines.push(`    and ${count - items.length} more`);
  return lines;
}

function validationLines(validation: Validation | null): string[] {
  if (validation === null) return ["  glTF validator: no result"];
  const { errors, warnings, infos, hints, issues, refused } = validation;
  const lines = [`  glTF validator ${validation.validator}: ${errors} errors, ${warnings} warnings, ${infos} infos, ${hints} hints`];
  for (const issue of issues.slice(0, LISTED_ISSUES)) lines.push(`    ${issue.severity} ${issue.code} at ${issue.pointer ?? "the file"}: ${issue.message}`);
  if (issues.length > LISTED_ISSUES) lines.push(`    and ${issues.length - LISTED_ISSUES} more in report.json`);
  for (const entry of refused) lines.push(`    not opened: ${entry}`);
  return lines;
}

function integrityLines(measurements: Measurements): string[] {
  const { faces, shells } = measurements;
  const lines = [
    `  surface: ${measurements.visibleTriangles} of ${measurements.triangles} triangles visible from outside, hidden ratio ${faces.hiddenRatio}${faces.sampled ? ` (estimated from ${faces.tested} faces)` : ""}; ${faces.degenerate} degenerate, ${faces.duplicate} duplicate faces; ${shells.count} shells, ${shells.closed} closed, ${shells.inverted} inside out`,
  ];
  if (measurements.uv.outsideUnitSquare > 0) lines.push(`  uv: ${measurements.uv.outsideUnitSquare} of the mapped surface has UVs outside 0-1, wrapped for coverage and overlap`);
  if (measurements.unitScale !== 1) lines.push(`  units: the .blend scale ${measurements.unitScale} converted to metres`);
  if (measurements.references.unresolved.length > 0) lines.push(`  unresolved references: ${measurements.references.unresolved.slice(0, LISTED_ISSUES).join("; ")}`);
  return lines;
}

export function summarize(report: Omit<Report, "summary">): string {
  const title = report.spec.name ?? "asset";
  const lines = [`${report.passed ? "PASS" : "FAIL"}  ${title}  (${report.asset.path})`];
  if (report.failure) lines.push(`  ${report.failure.stage} failed: ${report.failure.message} [${report.failure.code}]`);
  const width = Math.max(0, ...report.rules.map((rule) => rule.rule.length));
  for (const rule of report.rules) {
    lines.push(`  ${rule.pass ? "pass" : "FAIL"}  ${rule.rule.padEnd(width)}  measured ${show(rule.measured)}; required ${comparison(rule.rule)}${show(rule.limit)}`);
  }
  const passed = report.rules.filter((rule) => rule.pass).length;
  lines.push(`  ${passed} of ${report.rules.length} rules pass`);
  if (report.measurements?.textures) lines.push(...textureLines(report.measurements.textures));
  if (report.validation !== undefined) lines.push(...validationLines(report.validation));
  if (report.package) lines.push(...packageLines(report.package));
  if (report.measurements) lines.push(...integrityLines(report.measurements), ...motionLines(report.measurements));
  if (report.measurements) lines.push(...naturalLines(report.measurements.natural));
  if (report.reference) lines.push(...referenceLines(report.reference));
  if (report.visual) lines.push(...visualLines(report.visual));
  if (report.device) lines.push(`  render: ${describeDevice(report.device)}`);
  if (report.renders) lines.push(...renderLines(report.renders));
  if (report.asset.setSha256 !== null) lines.push(`  delivery: ${report.asset.files.length} files, ${report.asset.setBytes} bytes, set sha256 ${report.asset.setSha256}`);
  if (report.container) lines.push(`  isolation: ${containerText(report.container)}`);
  if (report.sandbox) lines.push(`  sandbox: ${isolationText(report.sandbox)}`);
  if (report.renderSandbox && (!report.sandbox || isolationText(report.renderSandbox) !== isolationText(report.sandbox))) {
    lines.push(`  render sandbox: ${isolationText(report.renderSandbox)}`);
  }
  lines.push(`  time: ${timingText(report.timings)}`);
  return lines.join("\n");
}
