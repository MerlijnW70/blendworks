import { coreScores, type RankingSource } from "../../src/mcp/routing/core.js";
import { toolNameOf } from "../../src/mcp/routing/names.js";
import { type Workflow, WORKFLOWS } from "../../src/mcp/routing/workflows.js";
import { type Intent, loadIntents } from "./intents.js";
import { loadUsage } from "./usage.js";

export const CORE_DENOMINATORS = { buildScripts: 100, benchmarkTune: 160, workflows: 100 } as const;

export type CoreSourceName = keyof typeof CORE_DENOMINATORS;

function tally(names: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const name of names) counts[name] = (counts[name] ?? 0) + 1;
  return counts;
}

export interface CoreData {
  intents?: Intent[];
  workflows?: Workflow[];
}

export function coreSources(data: CoreData = {}): Record<CoreSourceName, RankingSource> {
  const usage = loadUsage();
  const intents = data.intents ?? loadIntents();
  const workflows = data.workflows ?? WORKFLOWS;
  return {
    buildScripts: { counts: Object.fromEntries(Object.entries(usage.counts).map(([name, count]) => [toolNameOf(name), count])), denominator: CORE_DENOMINATORS.buildScripts },
    benchmarkTune: { counts: tally(intents.filter((intent) => intent.split === "tune").flatMap((intent) => intent.expect)), denominator: CORE_DENOMINATORS.benchmarkTune },
    workflows: { counts: tally(workflows.flatMap((workflow) => workflow.steps)), denominator: CORE_DENOMINATORS.workflows },
  };
}

export function derivedCoreScores(data: CoreData = {}): Map<string, number> {
  return coreScores(Object.values(coreSources(data)));
}
