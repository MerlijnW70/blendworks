import { describeDevice, type RenderDevice } from "./device.js";
import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./rules.js";
import type { Isolation } from "./sandbox.js";

export type Failure = { stage: "spec" | "asset" | "blender" | "measure" | "device" | "render" | "closeups"; code: string; message: string };

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
  summary: string;
};

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
  if (/\.(min|minCoverage)$/.test(rule)) return "at least ";
  if (/\.(max|maxBytes|maxOverlap)$/.test(rule)) return "at most ";
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
