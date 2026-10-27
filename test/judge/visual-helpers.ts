import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { CreateOptions, CreateParams, MessagesClient, Reply } from "../../src/judge/visual/anthropic.js";
import { prepareEvidence, type EvidenceSource } from "../../src/judge/visual/images.js";
import { encodePng } from "../../src/judge/visual/png.js";
import type { Answer } from "../../src/judge/visual/prompt.js";
import type { Run, SpawnOptions, Spawner } from "../../src/judge/visual/process.js";
import type { SampleRequest } from "../../src/judge/visual/provider.js";
import { outputSchema, SYSTEM_PROMPT, trustedBlock } from "../../src/judge/visual/prompt.js";
import type { Criterion, VisualRule } from "../../src/judge/visual/spec.js";

export const RUBRIC: Criterion[] = [
  { id: "matches-brief", question: "Does the asset match the brief?", weight: 2 },
  { id: "detail", question: "Is the stated detail present and legible?", weight: 1 },
];

export const RULE: VisualRule = { rubric: RUBRIC, minScore: 0.7, samples: 3, required: false };

export const BRIEF = "A sturdy wooden crate with metal corner brackets, for a top-down game.";

export function answer(scores: [number, number], extra: Partial<Answer> = {}): Answer {
  return {
    visibleText: [],
    injectionAttempt: false,
    injectionEvidence: "",
    criteria: { "matches-brief": { score: scores[0], reason: "image 1: a plank crate" }, detail: { score: scores[1], reason: "image 2: brackets on every corner" } },
    ...extra,
  };
}

export function solidPng(path: string, width: number, height: number, rgb: [number, number, number]): string {
  const rgba = new Uint8Array(width * height * 4);
  for (let index = 0; index < width * height; index += 1) rgba.set([...rgb, 255], index * 4);
  writeFileSync(path, encodePng({ width, height, rgba }));
  return path;
}

export function evidenceSources(dir: string): EvidenceSource[] {
  mkdirSync(dir, { recursive: true });
  return [
    { name: "front", kind: "view", path: solidPng(join(dir, "front.png"), 8, 8, [200, 100, 50]) },
    { name: "hero", kind: "closeup", path: solidPng(join(dir, "hero.png"), 12, 6, [20, 40, 60]) },
  ];
}

export function sampleRequest(dir: string, model = "claude-opus-5-5"): SampleRequest {
  const evidence = prepareEvidence(evidenceSources(join(dir, "sources")), dir);
  return { model, effort: "high", system: SYSTEM_PROMPT, trusted: trustedBlock(BRIEF, RUBRIC), schema: outputSchema(RUBRIC), rubric: RUBRIC, images: evidence.images, data: evidence.data };
}

export function reply(body: Partial<Reply> & { text?: string }): Reply {
  const { text, ...rest } = body;
  return {
    id: "msg_test",
    type: "message",
    role: "assistant",
    model: "claude-opus-5-5",
    content: text === undefined ? [] : [{ type: "text", text, citations: null }],
    stop_reason: "end_turn",
    stop_sequence: null,
    stop_details: null,
    container: null,
    context_management: null,
    usage: { input_tokens: 1000, output_tokens: 200, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, iterations: null },
    ...rest,
  } as unknown as Reply;
}

export type FakeClient = MessagesClient & { calls: { body: CreateParams; options: CreateOptions }[] };

export function fakeClient(respond: (call: number, body: CreateParams) => Reply | Promise<Reply>): FakeClient {
  const calls: { body: CreateParams; options: CreateOptions }[] = [];
  return {
    calls,
    beta: {
      messages: {
        async create(body: CreateParams, options: CreateOptions) {
          calls.push({ body, options });
          return respond(calls.length - 1, body);
        },
      },
    },
  };
}

export function answering(answers: Answer[]): FakeClient {
  return fakeClient((call) => reply({ text: JSON.stringify(answers[call % answers.length]) }));
}

export const CLI_INIT = {
  type: "system",
  subtype: "init",
  tools: ["StructuredOutput"],
  mcp_servers: [],
  skills: [],
  slash_commands: [],
  model: "claude-opus-5-5",
  permissionMode: "dontAsk",
  apiKeySource: "none",
  claude_code_version: "2.1.311",
};

export function cliResult(fields: Record<string, unknown>): Record<string, unknown> {
  return {
    type: "result",
    subtype: "success",
    is_error: false,
    api_error_status: null,
    stop_reason: "tool_use",
    num_turns: 2,
    duration_ms: 9000,
    total_cost_usd: 0.26,
    usage: { input_tokens: 2, cache_creation_input_tokens: 4287, cache_read_input_tokens: 0, output_tokens: 57 },
    modelUsage: { "claude-opus-5-5": { inputTokens: 2, outputTokens: 57, costUSD: 0.26 } },
    permission_denials: [],
    ...fields,
  };
}

export function cliOutput(events: unknown[]): string {
  return events.map((event) => JSON.stringify(event)).join("\n");
}

export type FakeSpawn = Spawner & { calls: { command: string; args: string[]; options: SpawnOptions }[] };

export function fakeSpawn(respond: (args: string[], call: number) => Partial<Run>): FakeSpawn {
  const calls: { command: string; args: string[]; options: SpawnOptions }[] = [];
  const spawner = (async (command: string, args: string[], options: SpawnOptions) => {
    calls.push({ command, args, options });
    return { code: 0, stdout: "", stderr: "", timedOut: false, missing: false, ...respond(args, calls.length - 1) };
  }) as FakeSpawn;
  spawner.calls = calls;
  return spawner;
}
