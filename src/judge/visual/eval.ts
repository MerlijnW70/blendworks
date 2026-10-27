import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { z } from "zod";
import type { Report } from "../report.js";
import type { JudgeOptions } from "../run.js";
import { addUsage, emptyUsage, type Usage } from "./prices.js";
import { displayText } from "./prompt.js";
import type { VisualStatus } from "./record.js";

const labelledSchema = z.strictObject({
  $schema: z.string().optional(),
  entries: z
    .array(
      z.strictObject({
        id: z.string().regex(/^[a-z0-9][a-z0-9-]{0,59}$/),
        asset: z.string().min(1),
        spec: z.string().min(1),
        expected: z.enum(["pass", "fail"]),
        note: z.string().max(300).optional(),
      }),
    )
    .min(1)
    .refine((entries) => new Set(entries.map((entry) => entry.id)).size === entries.length, { message: "entry ids must not repeat" }),
});

export type LabelledSet = z.infer<typeof labelledSchema>;

export class EvalError extends Error {}

export function readLabelled(path: string): LabelledSet {
  let value: unknown;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new EvalError(`cannot read the labelled set ${path}: ${(error as Error).message.split("\n")[0]}`);
  }
  const parsed = labelledSchema.safeParse(value);
  if (!parsed.success) throw new EvalError(`${path} is not a labelled set: ${parsed.error.issues.map((issue) => `${issue.path.join(".")} ${issue.message}`).join("; ")}`);
  return parsed.data;
}

export function resolveEntryPath(value: string, base: string, dirs: Record<string, string>): string {
  const named = /^\$([a-z][a-z0-9_-]*)\/(.+)$/i.exec(value);
  if (named === null) return resolve(base, value);
  const root = dirs[named[1]!];
  if (root === undefined) throw new EvalError(`${value} needs --dir ${named[1]}=<folder>`);
  return resolve(root, named[2]!);
}

export type EvalEntry = {
  id: string;
  expected: "pass" | "fail";
  predicted: "pass" | "fail";
  status: VisualStatus;
  score: number | null;
  reason: string | null;
  injection: boolean;
  verdict: boolean;
  costUsd: number | null;
  usage: Usage;
  report: string;
};

export type EvalReport = {
  labelled: string;
  total: number;
  agreed: number;
  agreement: number;
  falsePasses: string[];
  falseFails: string[];
  inconclusive: string[];
  costUsd: number | null;
  usage: Usage;
  entries: EvalEntry[];
};

export type EvalOptions = {
  labelledPath: string;
  outDir: string;
  dirs: Record<string, string>;
  judge: (options: JudgeOptions) => Promise<Report>;
  judgeOptions?: Partial<JudgeOptions>;
  progress?: (line: string) => void;
};

function entryResult(id: string, expected: "pass" | "fail", report: Report, reportPath: string): EvalEntry {
  const visual = report.visual ?? null;
  const status: VisualStatus = visual?.status ?? "inconclusive";
  const reason = visual?.reason ?? (visual === null ? `no visual result${report.failure ? `: ${report.failure.stage} failed: ${report.failure.message}` : ""}` : null);
  return {
    id,
    expected,
    predicted: status === "pass" ? "pass" : "fail",
    status,
    score: visual?.score ?? null,
    reason,
    injection: visual?.injection.flagged ?? false,
    verdict: report.passed,
    costUsd: visual?.costUsd ?? null,
    usage: visual?.usage ?? emptyUsage(),
    report: reportPath,
  };
}

export function summariseEval(labelled: string, entries: EvalEntry[]): EvalReport {
  const agreed = entries.filter((entry) => entry.predicted === entry.expected).length;
  return {
    labelled,
    total: entries.length,
    agreed,
    agreement: entries.length === 0 ? 0 : agreed / entries.length,
    falsePasses: entries.filter((entry) => entry.predicted === "pass" && entry.expected === "fail").map((entry) => entry.id),
    falseFails: entries.filter((entry) => entry.predicted === "fail" && entry.expected === "pass").map((entry) => entry.id),
    inconclusive: entries.filter((entry) => entry.status === "inconclusive").map((entry) => entry.id),
    costUsd: entries.some((entry) => entry.costUsd === null) ? null : entries.reduce((sum, entry) => sum + entry.costUsd!, 0),
    usage: entries.reduce((sum, entry) => addUsage(sum, entry.usage), emptyUsage()),
    entries,
  };
}

export async function visualEval(options: EvalOptions): Promise<EvalReport> {
  const labelledPath = resolve(options.labelledPath);
  const labelled = readLabelled(labelledPath);
  const base = dirname(labelledPath);
  const jobs = labelled.entries.map((entry) => ({ entry, specPath: resolveEntryPath(entry.spec, base, options.dirs), assetPath: resolveEntryPath(entry.asset, base, options.dirs) }));
  const outDir = resolve(options.outDir);
  mkdirSync(outDir, { recursive: true });
  const entries: EvalEntry[] = [];
  for (const { entry, specPath, assetPath } of jobs) {
    const entryOut = join(outDir, entry.id);
    const report = await options.judge({ ...options.judgeOptions, specPath, assetPath, outDir: entryOut });
    const result = entryResult(entry.id, entry.expected, report, join(entryOut, "report.json"));
    entries.push(result);
    options.progress?.(`${result.predicted === result.expected ? "agree   " : "DISAGREE"}  ${entry.id}: expected ${result.expected}, visual ${result.status}${result.score === null ? "" : ` ${result.score.toFixed(3)}`}`);
  }
  const report = summariseEval(labelledPath, entries);
  writeFileSync(join(outDir, "visual-eval.json"), `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

export function evalText(report: EvalReport): string {
  const lines = [
    `visual-eval: ${report.agreed} of ${report.total} agree (${(report.agreement * 100).toFixed(1)} %)`,
    `  false passes: ${report.falsePasses.length === 0 ? "none" : report.falsePasses.join(", ")}`,
    `  false fails: ${report.falseFails.length === 0 ? "none" : report.falseFails.join(", ")}`,
    `  inconclusive: ${report.inconclusive.length === 0 ? "none" : report.inconclusive.join(", ")}`,
    `  tokens: ${report.usage.inputTokens} input, ${report.usage.cacheCreationInputTokens} cache write, ${report.usage.cacheReadInputTokens} cache read, ${report.usage.outputTokens} output`,
    `  cost: ${report.costUsd === null ? "unknown" : `about ${report.costUsd.toFixed(4)} USD`}`,
  ];
  for (const entry of report.entries.filter((item) => item.predicted !== item.expected)) lines.push(`  ${entry.id}: expected ${entry.expected}, got ${entry.status}${entry.reason ? ` (${displayText(entry.reason, 160)})` : ""}`);
  return lines.join("\n");
}
