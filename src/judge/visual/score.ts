import type { Answer } from "./prompt.js";
import type { CommitteeRule, Criterion } from "./spec.js";

export function median(values: readonly number[]): number {
  if (values.length === 0) throw new Error("the median of no values");
  const sorted = [...values].sort((first, second) => first - second);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

export function majority(values: readonly number[]): number {
  if (values.length === 0) throw new Error("the majority of no values");
  const sorted = [...values].sort((first, second) => second - first);
  return sorted[Math.floor(values.length / 2)]!;
}

export function combine(values: readonly number[], rule: CommitteeRule): number {
  if (values.length === 0) throw new Error("no values to combine");
  return rule === "min" ? Math.min(...values) : majority(values);
}

export function weightedMean(rubric: readonly Criterion[], scores: Record<string, number>): number {
  const total = rubric.reduce((sum, item) => sum + item.weight, 0);
  return rubric.reduce((sum, item) => sum + item.weight * scores[item.id]!, 0) / total;
}

export function quorum(samples: number): number {
  return Math.floor(samples / 2) + 1;
}

export type CriterionScore = { id: string; weight: number; medians: Record<string, number>; score: number };

export function criterionScores(rubric: readonly Criterion[], answersByModel: Record<string, Answer[]>, rule: CommitteeRule): CriterionScore[] | null {
  const models = Object.keys(answersByModel);
  if (models.length === 0 || models.some((model) => answersByModel[model]!.length === 0)) return null;
  return rubric.map((item) => {
    const medians = Object.fromEntries(models.map((model) => [model, median(answersByModel[model]!.map((answer) => answer.criteria[item.id]!.score))]));
    return { id: item.id, weight: item.weight, medians, score: combine(Object.values(medians), rule) };
  });
}

export function overallScore(rubric: readonly Criterion[], scores: CriterionScore[]): number {
  return weightedMean(rubric, Object.fromEntries(scores.map((entry) => [entry.id, entry.score])));
}
