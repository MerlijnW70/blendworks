import { rankCore } from "../../src/mcp/routing/core.js";
import { toolNameOf } from "../../src/mcp/routing/names.js";
import { WORKFLOWS } from "../../src/mcp/routing/workflows.js";
import { type Intent, loadIntents } from "./intents.js";
import { loadUsage } from "./usage.js";

export const CORE_CANDIDATES = 24;

function tally(names: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const name of names) counts[name] = (counts[name] ?? 0) + 1;
  return counts;
}

export function coreSources(intents: Intent[] = loadIntents()): Record<string, Record<string, number>> {
  const usage = loadUsage();
  return {
    buildScripts: Object.fromEntries(Object.entries(usage.counts).map(([name, count]) => [toolNameOf(name), count])),
    benchmarkTune: tally(intents.filter((intent) => intent.split === "tune").flatMap((intent) => intent.expect)),
    workflows: tally(WORKFLOWS.flatMap((workflow) => workflow.steps)),
  };
}

export function derivedCoreRanking(): string[] {
  return rankCore(Object.values(coreSources())).slice(0, CORE_CANDIDATES);
}
