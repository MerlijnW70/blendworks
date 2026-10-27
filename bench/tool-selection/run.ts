import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { withSlot } from "../../scripts/lib/slots.js";
import { baselineRanker } from "./baseline-router.js";
import { ask, claudeAvailable } from "./claude.js";
import { type E2eScore, runE2e, systemPrompt } from "./e2e.js";
import { type Intent, loadIntents, missingTools } from "./intents.js";
import { estimateTokens, listingBytes, type RoutingScore, scoreRouting } from "./metrics.js";
import { legacyListing, MODES } from "./modes.js";
import { startBenchServer } from "./server.js";

const RESULTS = fileURLToPath(new URL("./results", import.meta.url));

const { values } = parseArgs({
  options: {
    e2e: { type: "string" },
    model: { type: "string", default: "sonnet" },
    effort: { type: "string", default: "low" },
    modes: { type: "string" },
    label: { type: "string", default: "current" },
    "measure-tokens": { type: "boolean", default: false },
    ids: { type: "string" },
    split: { type: "string", default: "heldout" },
  },
});

export function e2eSample(intents: Intent[], size: number, split: string = "heldout"): Intent[] {
  const heldout = intents.filter((intent) => intent.split === split);
  const queues = (["near-miss", "single", "multi-step"] as const).map((kind) => heldout.filter((intent) => intent.kind === kind));
  const sample: Intent[] = [];
  while (sample.length < Math.min(size, heldout.length)) {
    for (const queue of queues) {
      const next = queue.shift();
      if (next !== undefined && sample.length < size) sample.push(next);
    }
  }
  return sample;
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)} %`;
}

function routingLine(name: string, score: RoutingScore): string {
  const near = score.byKind["near-miss"];
  return `${name.padEnd(34)} top-1 ${percent(score.top1.rate).padStart(7)}  top-5 ${percent(score.top5.rate).padStart(7)}  near-miss top-1 ${percent(near.top1.rate).padStart(7)}  (${score.top5.total} intents, ${score.msPerQuery.mean} ms mean, ${score.msPerQuery.max} ms max)`;
}

async function main(): Promise<void> {
  const intents = loadIntents();
  const wanted = values.modes === undefined ? Object.keys(MODES) : values.modes.split(",");
  const report: Record<string, unknown> = { label: values.label, intents: { total: intents.length, heldout: intents.filter((intent) => intent.split === "heldout").length } };
  await withSlot(async () => {
    const server = await startBenchServer();
    try {
      const full = await server.connect("bench-full", MODES[wanted[0]!]!.full);
      const fullListing = await full.listing();
      const schemas = new Map<string, Tool["inputSchema"]>(fullListing.tools.map((tool) => [tool.name, tool.inputSchema]));
      report["coverage"] = missingTools(intents, fullListing.tools.map((tool) => tool.name).filter((name) => name !== "blender_find_tools" && name !== "blender_call"));
      const listings: Record<string, unknown> = {};
      const routing: Record<string, unknown> = {};
      const e2e: Record<string, E2eScore> = {};
      const legacy = legacyListing(fullListing.tools);
      const legacyBytes = listingBytes(legacy);
      listings["legacy"] = { tools: legacy.length, bytes: legacyBytes, estimatedTokens: estimateTokens(legacyBytes), note: "every tool with the bridge descriptions only: the listing before routing" };
      console.log(`${"legacy".padEnd(10)} ${String(legacy.length).padStart(3)} tools listed, ${legacyBytes} bytes, about ${estimateTokens(legacyBytes)} tokens`);
      const baseline = baselineRanker(legacy);
      routing["baseline BM25, heldout"] = scoreRouting(intents, baseline, "heldout");
      routing["baseline BM25, probe"] = scoreRouting(intents, baseline, "probe");
      routing["baseline BM25, all"] = scoreRouting(intents, baseline);
      for (const mode of wanted) {
        const spec = MODES[mode];
        if (spec === undefined) throw new Error(`unknown mode ${mode}; the modes are ${Object.keys(MODES).join(", ")}`);
        const client = await server.connect(`bench-${mode}`, spec.parts);
        const listing = await client.listing();
        const bytes = listingBytes(listing.tools);
        listings[mode] = { tools: listing.tools.length, bytes, estimatedTokens: estimateTokens(bytes), instructionsBytes: Buffer.byteLength(listing.instructions, "utf8"), names: listing.tools.map((tool) => tool.name) };
        console.log(`${mode.padEnd(10)} ${String(listing.tools.length).padStart(3)} tools listed, ${bytes} bytes, about ${estimateTokens(bytes)} tokens`);
        if (values["measure-tokens"]) {
          if (!claudeAvailable()) throw new Error("--measure-tokens needs the claude CLI on PATH or BLENDWORKS_CLAUDE");
          const settings = { model: values.model, effort: values.effort };
          const total = async (tools: Tool[]) => {
            const reply = await ask(systemPrompt({ tools, instructions: listing.instructions }), "User request: say ok", settings);
            return reply.firstTurn;
          };
          const measured = (await total(listing.tools)) - (await total([]));
          (listings[mode] as Record<string, unknown>)["measuredTokens"] = { tokens: measured, model: values.model, bytesPerToken: Math.round((bytes / measured) * 100) / 100 };
          console.log(`${mode.padEnd(10)} measured ${measured} tokens with ${values.model}, ${(bytes / measured).toFixed(2)} bytes per token`);
        }
        const ranker = spec.ranker?.(server.commands);
        if (ranker !== undefined) {
          routing[`${mode} router, heldout`] = scoreRouting(intents, ranker, "heldout");
          routing[`${mode} router, tune`] = scoreRouting(intents, ranker, "tune");
          routing[`${mode} router, probe`] = scoreRouting(intents, ranker, "probe");
          routing[`${mode} router, all`] = scoreRouting(intents, ranker);
        }
        if (values.e2e !== undefined) {
          if (!claudeAvailable()) throw new Error("--e2e needs the claude CLI on PATH or BLENDWORKS_CLAUDE");
          const sample = values.ids === undefined ? e2eSample(intents, Number(values.e2e), values.split) : intents.filter((intent) => values.ids!.split(",").includes(intent.id));
          e2e[mode] = await runE2e(mode, sample, client, schemas, { model: values.model, effort: values.effort }, (line) => console.log(line));
        }
        await client.close();
      }
      await full.close();
      report["listings"] = listings;
      report["routing"] = routing;
      if (values.e2e !== undefined) report["e2e"] = e2e;
      for (const [name, score] of Object.entries(routing)) console.log(routingLine(name, score as RoutingScore));
      for (const score of Object.values(e2e)) {
        console.log(`e2e ${score.mode.padEnd(8)} ${score.model}/${score.effort}, ${score.samples} tasks (${score.failed} failed): accuracy ${percent(score.accuracy.rate)}, near-miss ${percent(score.nearMiss.rate)} of ${score.nearMiss.total}, multi-step ${percent(score.multiStep.rate)}, run_python ${percent(score.runPython.rate)}, valid arguments ${percent(score.validArguments.rate)}, ${score.searchesPerTask} searches and ${score.inputTokensPerTask} input tokens per task, ${score.costUsd} USD`);
      }
      const coverage = report["coverage"] as ReturnType<typeof missingTools>;
      if (coverage.unknown.length > 0) console.log(`intents name tools the server does not list: ${coverage.unknown.join(", ")}`);
      if (coverage.uncovered.length > 0) console.log(`tools without an intent: ${coverage.uncovered.join(", ")}`);
    } finally {
      await server.close();
    }
  }, { label: "bench:tools" });
  mkdirSync(RESULTS, { recursive: true });
  const file = join(RESULTS, `${values.label}.json`);
  writeFileSync(file, `${JSON.stringify(report, null, 1)}\n`);
  console.log(`wrote ${file}`);
}

await main();
