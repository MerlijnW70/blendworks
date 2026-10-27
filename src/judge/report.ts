import { describeDevice, type RenderDevice } from "./device.js";
import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./rules.js";
import type { Isolation } from "./sandbox.js";
import type { Validation } from "./validator.js";

export type Failure = { stage: "spec" | "asset" | "validate" | "blender" | "measure" | "device" | "render" | "closeups"; code: string; message: string };

export const STAGES = ["measure", "device", "render", "sheet"] as const;

export type Timings = Record<(typeof STAGES)[number], number | null> & { total: number };

export type Report = {
  passed: boolean;
  preview: boolean;
  spec: { path: string; sha256: string | null; name: string | null };
  asset: { path: string; sha256: string | null; bytes: number | null };
  blender: string | null;
  sandbox: Isolation | null;
  renderSandbox: Isolation | null;
  device: RenderDevice | null;
  failure: Failure | null;
  rules: RuleResult[];
  measurements: Measurements | null;
  renders: { viewsSkipped: boolean; views: { view: string; path: string }[]; contactSheet: string } | null;
  timings: Timings;
  validation?: Validation | null;
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
  if (rule.startsWith("size.")) return "between ";
  return "";
}

export function isolationText(isolation: Isolation): string {
  return `network ${isolation.network}; memory ${isolation.memory}; timeout ${isolation.timeoutMs / 1000} s`;
}

export function timingText(timings: Timings): string {
  const stages = STAGES.flatMap((stage) => (timings[stage] === null ? [] : [`${stage} ${timings[stage].toFixed(2)} s`]));
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
  if (report.preview) lines.push("  views: skipped (preview); the rules alone decide pass or fail");
  if (report.device) lines.push(`  render: ${describeDevice(report.device)}`);
  if (report.renders) lines.push(`  contact sheet: ${report.renders.contactSheet}`);
  if (report.sandbox) lines.push(`  sandbox: ${isolationText(report.sandbox)}`);
  if (report.renderSandbox && (!report.sandbox || isolationText(report.renderSandbox) !== isolationText(report.sandbox))) {
    lines.push(`  render sandbox: ${isolationText(report.renderSandbox)}`);
  }
  lines.push(`  time: ${timingText(report.timings)}`);
  return lines.join("\n");
}
