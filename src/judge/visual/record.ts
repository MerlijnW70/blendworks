import type { EvidenceImage } from "./images.js";
import type { Usage } from "./prices.js";
import { displayText, type Answer } from "./prompt.js";
import type { SampleFailure } from "./provider.js";
import type { CommitteeRule, Criterion, Effort, ProviderName } from "./spec.js";

export const RECORD_VERSION = 1;
export const SCORE_RULE = "the weighted mean, by rubric weight, of each criterion's median score across the samples";
export const COMMITTEE_TEXT: Record<CommitteeRule, string> = {
  min: "each criterion takes the lowest of the models' medians",
  majority: "each criterion takes the highest score that a strict majority of the models' medians reach",
};

export type VisualStatus = "pass" | "fail" | "inconclusive";

export type InjectionFinding = { model: string; sample: number; source: "model" | "transcript"; text: string };

export type SampleRecord = {
  model: string;
  index: number;
  status: "ok" | "malformed" | "refused" | "error";
  servedBy: string | null;
  stopReason: string | null;
  stopDetails: unknown;
  failure: SampleFailure | null;
  answer: Answer | null;
  raw: string | null;
  usage: Usage;
  costUsd: number | null;
  costSource: "price-table" | "provider" | null;
  meta: Record<string, unknown>;
};

export type VisualRequestRecord = {
  provider: ProviderName | null;
  providerSource: string | null;
  providerSettings: Record<string, unknown> | null;
  models: string[];
  modelSource: string;
  effort: Effort;
  samples: number;
  quorum: number;
  committee: CommitteeRule | null;
  imageCap: number;
  system: string;
  systemSha256: string;
  trusted: string;
  trustedSha256: string;
  schema: Record<string, unknown>;
  calls: Record<string, unknown>;
};

export type VisualRecord = {
  version: number;
  status: VisualStatus;
  required: boolean;
  reason: string | null;
  score: number | null;
  minScore: number;
  rule: string;
  rubric: Criterion[];
  criteria: { id: string; weight: number; medians: Record<string, number>; score: number }[] | null;
  injection: { flagged: boolean; findings: InjectionFinding[] };
  request: VisualRequestRecord | null;
  images: EvidenceImage[];
  samples: SampleRecord[];
  usage: Usage;
  costUsd: number | null;
  costNote: string;
};

export type VisualRuleResult = { rule: string; measured: unknown; limit: unknown; pass: boolean };

export function visualRules(record: VisualRecord | null | undefined): VisualRuleResult[] {
  if (!record?.required) return [];
  const measured = record.status === "inconclusive" ? `inconclusive: ${record.reason}` : record.score;
  return [{ rule: "visual.minScore", measured, limit: record.minScore, pass: record.status === "pass" }];
}

function shown(score: number | null): string {
  return score === null ? "none" : score.toFixed(3);
}

export function visualLines(record: VisualRecord): string[] {
  const role = record.required ? "required" : "advisory, does not change the verdict";
  const word = record.status === "pass" ? "pass" : record.status === "fail" ? "FAIL" : "INCONCLUSIVE";
  const how = record.request ? `; ${record.request.models.join(", ")} via ${record.request.provider ?? "no provider"}, ${record.samples.length} samples` : "";
  const cost = record.costUsd === null ? "" : `, about ${record.costUsd.toFixed(4)} USD`;
  const lines = [`  visual (${role}): ${word}, score ${shown(record.score)}, at least ${record.minScore}${how}${cost}`];
  if (record.reason !== null) lines.push(`    reason: ${displayText(record.reason, 240)}`);
  for (const entry of record.criteria ?? []) {
    const answers = record.samples.flatMap((sample) => (sample.answer?.criteria[entry.id] ? [sample.answer.criteria[entry.id]!] : []));
    const closest = answers.reduce<{ score: number; reason: string } | null>((best, item) => (best === null || Math.abs(item.score - entry.score) < Math.abs(best.score - entry.score) ? item : best), null);
    const example = closest?.reason ?? "";
    lines.push(`    ${entry.id} ${shown(entry.score)} (weight ${entry.weight}): ${displayText(example, 160)}`);
  }
  for (const finding of record.injection.findings.slice(0, 5)) lines.push(`    injection flagged by the ${finding.source} of ${finding.model} sample ${finding.sample + 1}: ${displayText(finding.text, 160)}`);
  return lines;
}
