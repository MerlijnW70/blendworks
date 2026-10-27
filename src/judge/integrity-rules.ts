import type { Measurements } from "./measurements.js";
import type { RuleResult } from "./shape-rules.js";
import type { AssetSpec } from "./spec.js";

export type RenderOutcome = { status: "rendered" | "preview" | "skipped" | "failed"; reason: string | null };

function atMost(results: RuleResult[], rule: string, measured: number, limit: number | undefined): void {
  if (limit !== undefined) results.push({ rule, measured, limit, pass: measured <= limit });
}

export function manifoldRequired(spec: AssetSpec): boolean {
  return spec.manifold === true || (typeof spec.manifold === "object" && spec.manifold.required === true);
}

export function manifoldRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const results: RuleResult[] = [];
  if (manifoldRequired(spec)) {
    const { nonManifoldEdges, boundaryEdges, wireEdges, nonManifoldVertices, looseVertices, looseParts } = measurements.manifold;
    const defects = { nonManifoldEdges, boundaryEdges, wireEdges, nonManifoldVertices, looseVertices };
    results.push({
      rule: "manifold",
      measured: { ...defects, looseParts },
      limit: { nonManifoldEdges: 0, boundaryEdges: 0, wireEdges: 0, nonManifoldVertices: 0, looseVertices: 0 },
      pass: Object.values(defects).every((value) => value === 0),
    });
  }
  if (typeof spec.manifold === "object" && spec.manifold.noInverted === true) {
    const { inverted, closed } = measurements.shells;
    results.push({ rule: "manifold.noInverted", measured: { invertedShells: inverted, closedShells: closed }, limit: { invertedShells: 0 }, pass: inverted === 0 });
  }
  return results;
}

export function surfaceRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const results: RuleResult[] = [];
  const { faces, shells } = measurements;
  if (spec.triangles?.minVisible !== undefined) {
    const measured = measurements.visibleTriangles;
    results.push({ rule: "triangles.minVisible", measured, limit: spec.triangles.minVisible, pass: measured >= spec.triangles.minVisible });
  }
  atMost(results, "faces.maxDegenerate", faces.degenerate, spec.faces?.maxDegenerate);
  atMost(results, "faces.maxDuplicate", faces.duplicate, spec.faces?.maxDuplicate);
  atMost(results, "faces.maxHiddenRatio", faces.hiddenRatio, spec.faces?.maxHiddenRatio);
  atMost(results, "shells.max", shells.count, spec.shells?.max);
  return results;
}

export function selfContainedRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  if (spec.selfContained !== true) return [];
  const { unresolved } = measurements.references;
  const refused = measurements.externalFilesRefused;
  const missing = [...unresolved, ...refused.map((entry) => `${entry}: refused, outside the delivery`)];
  return [{ rule: "selfContained", measured: { unresolved: missing.length, references: missing.slice(0, 10) }, limit: { unresolved: 0 }, pass: missing.length === 0 }];
}

export function renderRules(spec: AssetSpec, outcome: RenderOutcome | null): RuleResult[] {
  if (spec.renders?.required !== true) return [];
  const status = outcome?.status ?? "failed";
  return [{ rule: "renders.required", measured: outcome?.reason ? `${status}: ${outcome.reason}` : status, limit: "rendered", pass: status === "rendered" }];
}
