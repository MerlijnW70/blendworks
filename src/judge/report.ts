import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./rules.js";
import type { Isolation } from "./sandbox.js";

export type Failure = { stage: "spec" | "asset" | "blender" | "measure" | "render"; code: string; message: string };

export type Report = {
  passed: boolean;
  spec: { path: string; sha256: string | null; name: string | null };
  asset: { path: string; sha256: string | null; bytes: number | null };
  blender: string | null;
  sandbox: Isolation | null;
  failure: Failure | null;
  rules: RuleResult[];
  measurements: Measurements | null;
  renders: { views: { view: string; path: string }[]; contactSheet: string } | null;
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
  if (report.renders) lines.push(`  contact sheet: ${report.renders.contactSheet}`);
  if (report.sandbox) lines.push(`  sandbox: network ${report.sandbox.network}; memory ${report.sandbox.memory}; timeout ${report.sandbox.timeoutMs / 1000} s`);
  return lines.join("\n");
}
