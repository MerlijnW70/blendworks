import { InfrastructureError } from "./isolation.js";
import type { Failure } from "./report.js";
import type { RuleResult } from "./shape-rules.js";

export const STAGE_INFRASTRUCTURE_CODES = ["timeout", "memory_cap", "file_lock"] as const;
type StageInfrastructureCode = (typeof STAGE_INFRASTRUCTURE_CODES)[number];

export type LostEvidence = "render" | "visual";

const RULE_NEEDS: Record<string, LostEvidence> = { "renders.required": "render", "natural.repetition": "render", "visual.minScore": "visual" };

export function isInfrastructure(failure: Failure | null | undefined): failure is Failure & { code: StageInfrastructureCode } {
  return failure !== null && failure !== undefined && (STAGE_INFRASTRUCTURE_CODES as readonly string[]).includes(failure.code);
}

export function infrastructureError(failure: Failure & { code: StageInfrastructureCode }): InfrastructureError {
  return new InfrastructureError(failure.code, `the ${failure.stage} stage hit a ${failure.code.replace("_", " ")} limit of this machine, so nothing was judged and this is not a verdict; judge again: ${failure.message}`);
}

export function unsettledBy(rules: readonly RuleResult[], lost: ReadonlySet<LostEvidence>): boolean {
  const failing = rules.filter((rule) => !rule.pass);
  if (lost.size === 0 || failing.length === 0) return false;
  return failing.every((rule) => {
    const needs = RULE_NEEDS[rule.rule];
    return needs !== undefined && lost.has(needs);
  });
}

export class EvidenceLedger {
  readonly lost = new Set<LostEvidence>();
  first: (Failure & { code: StageInfrastructureCode }) | null = null;

  note(failure: Failure | null | undefined, evidence: readonly LostEvidence[]): void {
    if (!isInfrastructure(failure)) return;
    for (const entry of evidence) this.lost.add(entry);
    this.first ??= failure;
  }

  settle(rules: readonly RuleResult[]): void {
    if (this.first !== null && unsettledBy(rules, this.lost)) throw infrastructureError(this.first);
  }
}
