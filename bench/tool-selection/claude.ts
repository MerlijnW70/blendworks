import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { childEnvironment, isolationProblem } from "../../src/judge/visual/claude-code.js";
import { findClaude, runProcess } from "../../src/judge/visual/process.js";

export const CHOICE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["tool", "arguments"],
  properties: {
    tool: { type: "string", description: "The exact name of the tool you call." },
    arguments: { type: "object", description: "The arguments of the call." },
  },
};

export interface ModelSettings {
  model: string;
  effort: string;
}

export interface Usage {
  input: number;
  cacheCreation: number;
  cacheRead: number;
  output: number;
}

export interface Reply {
  choice: { tool: string; arguments: Record<string, unknown> } | null;
  failure: string | null;
  usage: Usage;
  firstTurn: number;
  costUsd: number;
}

type Part = { type: string; name?: string; text?: string; input?: unknown };

function assistantParts(all: Event[]): Part[] {
  return all.flatMap((event) => (event.type === "assistant" ? (((event.message as { content?: unknown[] } | undefined)?.content ?? []) as Part[]) : []));
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function structured(value: unknown): { tool: string; arguments: Record<string, unknown> } | null {
  const output = record(value);
  return typeof output["tool"] === "string" ? { tool: output["tool"], arguments: record(output["arguments"]) } : null;
}

const REPLY_TIMEOUT_MS = 180_000;

type Event = Record<string, unknown>;

function events(stdout: string): Event[] {
  return stdout.split("\n").flatMap((line) => {
    if (!line.trim().startsWith("{")) return [];
    try {
      const value: unknown = JSON.parse(line);
      return value !== null && typeof value === "object" ? [value as Event] : [];
    } catch {
      return [];
    }
  });
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function claudeAvailable(): boolean {
  return findClaude(process.env) !== null;
}

export async function ask(system: string, prompt: string, settings: ModelSettings): Promise<Reply> {
  const command = findClaude(process.env);
  const empty: Usage = { input: 0, cacheCreation: 0, cacheRead: 0, output: 0 };
  if (command === null) return { choice: null, failure: "the claude CLI is not installed", usage: empty, firstTurn: 0, costUsd: 0 };
  const cwd = mkdtempSync(join(tmpdir(), "blendworks-routing-"));
  const systemFile = join(cwd, "system.txt");
  writeFileSync(systemFile, system);
  const args = [
    "--print",
    "--output-format",
    "stream-json",
    "--verbose",
    "--safe-mode",
    "--restricted",
    "--setting-sources",
    "",
    "--strict-mcp-config",
    "--tools",
    "",
    "--disable-slash-commands",
    "--permission-mode",
    "dontAsk",
    "--no-session-persistence",
    "--max-turns",
    "3",
    "--max-budget-usd",
    "2",
    "--model",
    settings.model,
    "--effort",
    settings.effort,
    "--system-prompt-file",
    systemFile,
    "--json-schema",
    JSON.stringify(CHOICE_SCHEMA),
  ];
  try {
    const run = await runProcess(command, args, { cwd, env: childEnvironment(process.env), timeoutMs: REPLY_TIMEOUT_MS, stdin: prompt });
    const all = events(run.stdout);
    const init = all.find((event) => event.type === "system" && event.subtype === "init");
    const result = [...all].reverse().find((event) => event.type === "result");
    const usageRecord = (result?.usage ?? {}) as Record<string, unknown>;
    const usage = { input: count(usageRecord.input_tokens), cacheCreation: count(usageRecord.cache_creation_input_tokens), cacheRead: count(usageRecord.cache_read_input_tokens), output: count(usageRecord.output_tokens) };
    const costUsd = count(result?.total_cost_usd);
    const firstUsage = ((all.find((event) => event.type === "assistant")?.message as { usage?: Record<string, unknown> } | undefined)?.usage ?? {}) as Record<string, unknown>;
    const firstTurn = count(firstUsage.input_tokens) + count(firstUsage.cache_creation_input_tokens) + count(firstUsage.cache_read_input_tokens);
    const problem = isolationProblem(init);
    if (problem !== null) return { choice: null, failure: problem, usage, firstTurn, costUsd };
    if (result === undefined) return { choice: null, failure: `no result (exit ${run.code}${run.timedOut ? ", timed out" : ""}): ${run.stderr.slice(-300)}`, usage, firstTurn, costUsd };
    const parts = assistantParts(all);
    const attempt = parts.find((part) => part.type === "tool_use");
    const direct = attempt !== undefined && attempt.name !== "StructuredOutput" ? { tool: String(attempt.name), arguments: record(attempt.input) } : null;
    const choice = direct ?? structured(result.structured_output) ?? structured(attempt?.input);
    if (choice === null) {
      const seen = parts.map((part) => (part.type === "tool_use" ? `tool_use ${part.name}` : `${part.type} ${String(part.text ?? "").slice(0, 120)}`));
      return { choice: null, failure: `no tool choice: ${String(result.subtype)} ${String(result.result ?? "").slice(0, 200)} [${seen.join(" | ")}]`, usage, firstTurn, costUsd };
    }
    return { choice, failure: null, usage, firstTurn, costUsd };
  } finally {
    rmSync(cwd, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
