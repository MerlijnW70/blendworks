import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { toolNameOf } from "../../src/mcp/routing/names.js";
import { ask, type ModelSettings, type Usage } from "./claude.js";
import { accepted, type Intent } from "./intents.js";
import { rate, type Rate } from "./metrics.js";
import type { BenchClient, Listing } from "./server.js";

export const SEARCH_TOOL = "blender_find_tools";
export const CALL_TOOL = "blender_call";
export const RUN_PYTHON_TOOL = "blender_run_python";
const MAX_SEARCHES = 2;
const WORKERS = 3;
const RESULT_CHARS = 60_000;

export interface Sample {
  id: string;
  kind: Intent["kind"];
  calls: { tool: string; arguments: Record<string, unknown> }[];
  final: string | null;
  correct: boolean;
  validArguments: boolean;
  failure: string | null;
  usage: Usage;
  promptTokens: number;
  costUsd: number;
}

export interface E2eScore {
  mode: string;
  model: string;
  effort: string;
  samples: number;
  failed: number;
  accuracy: Rate;
  nearMiss: Rate;
  multiStep: Rate;
  runPython: Rate;
  validArguments: Rate;
  searchesPerTask: number;
  inputTokensPerTask: number;
  costUsd: number;
  results: Sample[];
}

export function systemPrompt(listing: Listing): string {
  return [
    'You are an AI agent that builds 3D assets for a user. Your MCP client is connected to the server "blendworks".',
    "The server's instructions:",
    "<instructions>",
    listing.instructions,
    "</instructions>",
    "The tools the server lists, as JSON, exactly as your client received them from tools/list:",
    "<tools>",
    JSON.stringify(listing.tools),
    "</tools>",
    "The objects, materials and files the user names already exist, so do not inspect the scene first.",
    "For the user's request, decide the single next tool call you make: the call that carries out the request, or the first step of it. Use a tool from the list, or one that an earlier tool result in this conversation offers. Do not ask a question. Reply with the tool's exact name and its arguments; you do not call it yourself.",
  ].join("\n");
}

function decoded(value: unknown): unknown {
  if (typeof value !== "string" || !/^\s*([[{0-9.-]|true$|false$)/.test(value)) return value;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

export function clientArguments(args: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(args).map(([key, value]) => [key, decoded(value)]));
}

export function finalTool(choice: { tool: string; arguments: Record<string, unknown> }): { tool: string; arguments: Record<string, unknown> } {
  if (choice.tool !== CALL_TOOL) return { tool: toolNameOf(choice.tool), arguments: clientArguments(choice.arguments) };
  const inner = choice.arguments["tool"];
  const args = decoded(choice.arguments["arguments"]);
  if (typeof inner !== "string") return choice;
  const name = toolNameOf(inner.trim());
  if (name === CALL_TOOL && args !== null && typeof args === "object" && !Array.isArray(args)) return finalTool({ tool: CALL_TOOL, arguments: args as Record<string, unknown> });
  return { tool: name, arguments: args !== null && typeof args === "object" && !Array.isArray(args) ? clientArguments(args as Record<string, unknown>) : {} };
}

function resultText(content: unknown): string {
  const items = Array.isArray(content) ? (content as { type: string; text?: string }[]) : [];
  return items.flatMap((item) => (item.type === "text" && item.text !== undefined ? [item.text] : [])).join("\n").slice(0, RESULT_CHARS);
}

function validator(schemas: Map<string, Tool["inputSchema"]>): (tool: string, args: Record<string, unknown>) => boolean {
  const cache = new Map<string, z.ZodType>();
  return (tool, args) => {
    const schema = schemas.get(tool);
    if (schema === undefined) return false;
    let parser = cache.get(tool);
    if (parser === undefined) {
      parser = z.fromJSONSchema(schema as Parameters<typeof z.fromJSONSchema>[0]);
      cache.set(tool, parser);
    }
    return parser.safeParse(args).success;
  };
}

async function runSample(intent: Intent, system: string, client: BenchClient, settings: ModelSettings, valid: (tool: string, args: Record<string, unknown>) => boolean): Promise<Sample> {
  const usage: Usage = { input: 0, cacheCreation: 0, cacheRead: 0, output: 0 };
  const calls: Sample["calls"] = [];
  const transcript: string[] = [`User request: ${intent.text}`];
  let costUsd = 0;
  let promptTokens = 0;
  for (let round = 0; round <= MAX_SEARCHES; round += 1) {
    const reply = await ask(system, transcript.join("\n\n"), settings);
    usage.input += reply.usage.input;
    usage.cacheCreation += reply.usage.cacheCreation;
    usage.cacheRead += reply.usage.cacheRead;
    usage.output += reply.usage.output;
    costUsd += reply.costUsd;
    promptTokens += reply.firstTurn;
    if (reply.choice === null) return { id: intent.id, kind: intent.kind, calls, final: null, correct: false, validArguments: false, failure: reply.failure, usage, promptTokens, costUsd };
    calls.push(reply.choice);
    if (reply.choice.tool !== SEARCH_TOOL || round === MAX_SEARCHES) {
      const final = finalTool(reply.choice);
      return { id: intent.id, kind: intent.kind, calls, final: final.tool, correct: accepted(intent, 0).has(final.tool), validArguments: valid(final.tool, final.arguments), failure: null, usage, promptTokens, costUsd };
    }
    const found = await client.call(SEARCH_TOOL, clientArguments(reply.choice.arguments));
    transcript.push(`You called ${SEARCH_TOOL} with ${JSON.stringify(reply.choice.arguments)}. It returned:\n<result>\n${resultText(found.content)}\n</result>\nDecide your next tool call.`);
  }
  return { id: intent.id, kind: intent.kind, calls, final: null, correct: false, validArguments: false, failure: "no final call", usage, promptTokens, costUsd };
}

export async function runE2e(mode: string, intents: Intent[], client: BenchClient, schemas: Map<string, Tool["inputSchema"]>, settings: ModelSettings, log: (line: string) => void): Promise<E2eScore> {
  const listing = await client.listing();
  const system = systemPrompt(listing);
  const valid = validator(schemas);
  const results: Sample[] = new Array(intents.length);
  let next = 0;
  const worker = async () => {
    while (next < intents.length) {
      const index = next;
      next += 1;
      const intent = intents[index]!;
      const sample = await runSample(intent, system, client, settings, valid);
      results[index] = sample;
      log(`${mode} ${index + 1}/${intents.length} ${intent.id}: ${sample.calls.map((call) => call.tool).join(" -> ")} => ${sample.final ?? sample.failure} ${sample.correct ? "ok" : "MISS"}`);
    }
  };
  await Promise.all(Array.from({ length: WORKERS }, worker));
  const answered = results.filter((sample) => sample.failure === null);
  const of = (filter: (sample: Sample) => boolean, hit: (sample: Sample) => boolean) => {
    const chosen = results.filter(filter);
    return rate(chosen.filter(hit).length, chosen.length);
  };
  const tokens = results.reduce((sum, sample) => sum + sample.promptTokens, 0);
  return {
    mode,
    model: settings.model,
    effort: settings.effort,
    samples: results.length,
    failed: results.length - answered.length,
    accuracy: of(() => true, (sample) => sample.correct),
    nearMiss: of((sample) => sample.kind === "near-miss", (sample) => sample.correct),
    multiStep: of((sample) => sample.kind === "multi-step", (sample) => sample.correct),
    runPython: of(() => true, (sample) => sample.final === RUN_PYTHON_TOOL),
    validArguments: of(() => true, (sample) => sample.validArguments),
    searchesPerTask: Math.round((results.reduce((sum, sample) => sum + sample.calls.filter((call) => call.tool === SEARCH_TOOL).length, 0) / Math.max(1, results.length)) * 100) / 100,
    inputTokensPerTask: Math.round(tokens / Math.max(1, results.length)),
    costUsd: Math.round(results.reduce((sum, sample) => sum + sample.costUsd, 0) * 1000) / 1000,
    results,
  };
}
