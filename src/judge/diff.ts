import { readFileSync } from "node:fs";
import { z } from "zod";

const ruleSchema = z.object({ rule: z.string(), measured: z.unknown(), limit: z.unknown(), pass: z.boolean() });

const viewSchema = z.object({ view: z.string(), path: z.string(), sha256: z.string().optional() });

const reportSchema = z.object({
  passed: z.boolean(),
  spec: z.object({ path: z.string(), sha256: z.string().nullable() }).passthrough(),
  asset: z.object({ path: z.string(), sha256: z.string().nullable(), setSha256: z.string().nullable().optional() }).passthrough(),
  failure: z.object({ stage: z.string(), code: z.string(), message: z.string() }).nullable(),
  rules: z.array(ruleSchema),
  measurements: z.record(z.string(), z.unknown()).nullable(),
  renders: z
    .object({ views: z.array(viewSchema), contactSheet: z.string().nullable(), contactSheetSha256: z.string().nullable().optional() })
    .passthrough()
    .nullable(),
});

export type JudgeReport = z.infer<typeof reportSchema>;

export type Change = { kind: "verdict" | "input" | "rule" | "measurement" | "image"; path: string; before: unknown; after: unknown };

export class ReportError extends Error {}

export function readReport(path: string): JudgeReport {
  let value: unknown;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new ReportError(`cannot read the report ${path}: ${(error as Error).message.split("\n")[0]}`);
  }
  const parsed = reportSchema.safeParse(value);
  if (!parsed.success) throw new ReportError(`${path} is not a judge report: ${parsed.error.issues[0]?.path.join(".") ?? "spec"} ${parsed.error.issues[0]?.message ?? ""}`.trim());
  return parsed.data;
}

function same(first: unknown, second: unknown): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

function leaves(value: unknown, path: string, into: Map<string, unknown>): void {
  if (Array.isArray(value) && value.some((entry) => entry !== null && typeof entry === "object")) {
    value.forEach((entry, index) => leaves(entry, `${path}[${index}]`, into));
    if (value.length === 0) into.set(path, []);
    return;
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) into.set(path, {});
    for (const [key, entry] of entries) leaves(entry, path === "" ? key : `${path}.${key}`, into);
    return;
  }
  into.set(path, value);
}

function compareMaps(kind: Change["kind"], before: Map<string, unknown>, after: Map<string, unknown>, changes: Change[]): void {
  const keys = [...new Set([...before.keys(), ...after.keys()])].sort();
  for (const key of keys) {
    const first = before.has(key) ? before.get(key) : undefined;
    const second = after.has(key) ? after.get(key) : undefined;
    if (!same(first, second)) changes.push({ kind, path: key, before: first ?? null, after: second ?? null });
  }
}

function images(report: JudgeReport): Map<string, unknown> {
  const found = new Map<string, unknown>();
  for (const view of report.renders?.views ?? []) found.set(view.view, view.sha256 ?? "no hash recorded");
  if (report.renders?.contactSheet) found.set("contact sheet", report.renders.contactSheetSha256 ?? "no hash recorded");
  return found;
}

export function diffReports(before: JudgeReport, after: JudgeReport): Change[] {
  const changes: Change[] = [];
  if (before.passed !== after.passed) changes.push({ kind: "verdict", path: "passed", before: before.passed, after: after.passed });
  if (!same(before.failure, after.failure)) changes.push({ kind: "verdict", path: "failure", before: before.failure, after: after.failure });
  const inputs = (report: JudgeReport) =>
    new Map<string, unknown>([
      ["spec sha256", report.spec.sha256],
      ["asset sha256", report.asset.sha256],
      ["delivery set sha256", report.asset.setSha256 ?? null],
    ]);
  compareMaps("input", inputs(before), inputs(after), changes);
  const rules = (report: JudgeReport) => new Map<string, unknown>(report.rules.map((rule) => [rule.rule, { pass: rule.pass, measured: rule.measured, limit: rule.limit }]));
  compareMaps("rule", rules(before), rules(after), changes);
  const measured = (report: JudgeReport) => {
    const found = new Map<string, unknown>();
    if (report.measurements !== null) leaves(report.measurements, "", found);
    return found;
  };
  compareMaps("measurement", measured(before), measured(after), changes);
  compareMaps("image", images(before), images(after), changes);
  return changes;
}

function show(value: unknown): string {
  if (value === null || value === undefined) return "(none)";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function ruleLine(change: Change): string {
  const before = change.before as { pass: boolean; measured: unknown; limit: unknown } | null;
  const after = change.after as { pass: boolean; measured: unknown; limit: unknown } | null;
  if (before === null) return `  + ${change.path}: ${after?.pass ? "pass" : "FAIL"}, measured ${show(after?.measured)}, required ${show(after?.limit)}`;
  if (after === null) return `  - ${change.path}: was ${before.pass ? "pass" : "FAIL"}, measured ${show(before.measured)}`;
  const parts = [];
  if (before.pass !== after.pass) parts.push(`${before.pass ? "pass" : "FAIL"} -> ${after.pass ? "pass" : "FAIL"}`);
  if (!same(before.measured, after.measured)) parts.push(`measured ${show(before.measured)} -> ${show(after.measured)}`);
  if (!same(before.limit, after.limit)) parts.push(`required ${show(before.limit)} -> ${show(after.limit)}`);
  return `  ~ ${change.path}: ${parts.join("; ")}`;
}

const HEADINGS: Record<Change["kind"], string> = { verdict: "verdict", input: "inputs", rule: "rules", measurement: "measurements", image: "images (sha256 per view)" };

export function diffText(before: JudgeReport, after: JudgeReport, changes: Change[]): string {
  const lines = [`A: ${before.passed ? "PASS" : "FAIL"}  ${before.asset.path}`, `B: ${after.passed ? "PASS" : "FAIL"}  ${after.asset.path}`];
  if (changes.length === 0) return [...lines, "no differences: same verdict, rules, measurements and images"].join("\n");
  for (const kind of Object.keys(HEADINGS) as Change["kind"][]) {
    const group = changes.filter((change) => change.kind === kind);
    if (group.length === 0) continue;
    lines.push(`${HEADINGS[kind]}: ${group.length} changed`);
    for (const change of group) lines.push(kind === "rule" ? ruleLine(change) : `  ~ ${change.path}: ${show(change.before)} -> ${show(change.after)}`);
  }
  return lines.join("\n");
}
