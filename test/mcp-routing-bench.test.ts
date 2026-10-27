import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { derivedCoreRanking } from "../bench/tool-selection/core-data.js";
import { loadIntents, missingTools } from "../bench/tool-selection/intents.js";
import { estimateTokens, listingBytes, scoreRouting } from "../bench/tool-selection/metrics.js";
import { productSearch } from "../bench/tool-selection/modes.js";
import { type BenchClient, type BenchServer, startBenchServer } from "../bench/tool-selection/server.js";
import { startHeadlessSession } from "../src/mcp/headless.js";
import { DEFERRED_TEXT_LIMIT, UPFRONT_TEXT_LIMIT } from "../src/mcp/instructions.js";
import { CORE_RANKING } from "../src/mcp/routing/core.js";
import { sampleObject } from "../src/mcp/routing/examples.js";
import { toolNameOf } from "../src/mcp/routing/names.js";
import { ArgumentCheck } from "../src/mcp/routing/validate.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";
import { texts } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

export const HELDOUT_TOP5_HITS = 70;
export const HELDOUT_TOP1_HITS = 62;
export const CORE_TOKEN_BUDGET = 16_500;
export const MAX_SEARCH_MS = 20;

const intents = loadIntents();
let server: BenchServer;
let all: Tool[];

function words(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

describe("tool routing on the real bridge", workBudget(240_000), () => {
  beforeAll(withWorkBudget(120_000, async () => {
    server = await startBenchServer((headless) => startHeadlessSession(headless));
    const client = await server.connect("routing-test", { toolsets: { kind: "all" } });
    all = (await client.listing()).tools;
    await client.close();
  }));

  afterAll(async () => {
    await server?.close();
  });

  it("gives every bridge command a family, example intents and a nearest alternative that exists", () => {
    const tools = new Set(all.map((tool) => tool.name));
    const offered = server.commands.map((command) => command.name);
    expect(offered).toContain("recover");
    for (const command of server.commands) {
      expect(command.family, command.name).toMatch(/^[a-z][a-z_]*$/);
      expect(command.intents.length, command.name).toBeGreaterThanOrEqual(1);
      expect(command.nearest.length, command.name).toBeGreaterThanOrEqual(1);
      for (const nearest of command.nearest) {
        expect(tools.has(toolNameOf(nearest.name)), `${command.name} -> ${nearest.name}`).toBe(true);
        expect(nearest.name, command.name).not.toBe(command.name);
      }
      if (!command.internal) expect(all.find((tool) => tool.name === toolNameOf(command.name))?.description, command.name).toContain(`Instead: ${toolNameOf(command.nearest[0]!.name)}`);
    }
  });

  it("takes its families from the bridge metadata, and the search filters by them", () => {
    const declared = new Set(server.commands.filter((command) => !command.internal).map((command) => command.family!));
    const finder = all.find((tool) => tool.name === "blender_find_tools")!;
    const offered = ((finder.inputSchema.properties!["families"] as { items: { enum: string[] } }).items.enum);
    expect(new Set(offered)).toEqual(new Set([...declared, "library"]));
    const search = productSearch(server.commands);
    expect(search.search("bake the textures", { families: ["uv"] }).every((match) => match.name.startsWith("blender_uv"))).toBe(true);
  });

  it("keeps the benchmark honest: every tool has an intent, intents name real tools, and no example intent copies one", () => {
    const tools = all.map((tool) => tool.name).filter((name) => name !== "blender_find_tools");
    expect(missingTools(intents, tools)).toEqual({ unknown: [], uncovered: ["blender_run_python"] });
    const benchmark = new Set(intents.map((intent) => words(intent.text)));
    for (const command of server.commands) for (const intent of command.intents) expect(benchmark.has(words(intent)), `${command.name}: ${intent}`).toBe(false);
    for (const workflow of WORKFLOWS) for (const step of workflow.steps) expect(tools, workflow.id).toContain(step);
  });

  it("routes the held-out intents at or above the reported accuracy, deterministically", () => {
    const search = productSearch(server.commands);
    const rank = (query: string) => search.search(query).map((match) => match.name);
    const first = scoreRouting(intents, rank, "heldout");
    const again = scoreRouting(intents, rank, "heldout");
    expect(again.misses).toEqual(first.misses);
    expect(first.top5.total).toBe(71);
    expect(first.top5.hits).toBeGreaterThanOrEqual(HELDOUT_TOP5_HITS);
    expect(first.top1.hits).toBeGreaterThanOrEqual(HELDOUT_TOP1_HITS);
    expect(first.top5.rate).toBeGreaterThanOrEqual(0.95);
  });

  it("answers a query in under 20 ms", () => {
    const search = productSearch(server.commands);
    for (const intent of intents) search.search(intent.text);
    for (const intent of intents) {
      const started = performance.now();
      search.search(intent.text, { limit: 5 });
      expect(performance.now() - started, intent.id).toBeLessThan(MAX_SEARCH_MS);
    }
  });

  it("keeps the default listing within the core token budget, at least 70 % below the full one", async () => {
    const client = await server.connect("routing-test-core");
    const core = (await client.listing()).tools;
    await client.close();
    const coreTokens = estimateTokens(listingBytes(core));
    expect(coreTokens).toBeLessThanOrEqual(CORE_TOKEN_BUDGET);
    expect(coreTokens).toBeLessThanOrEqual(0.3 * estimateTokens(listingBytes(all)));
    expect(core.map((tool) => tool.name)).toEqual(expect.arrayContaining(["blender_find_tools", "blender_call"]));
  });

  it("keeps every description within what Claude Code reads, with the search words first", async () => {
    const client = await server.connect("routing-test-lengths", { toolsets: { kind: "core", families: [] } });
    const core = (await client.listing()).tools;
    await client.close();
    const summaries = new Map(server.commands.map((command) => [toolNameOf(command.name), command.description]));
    for (const tool of [...all, ...core]) {
      const description = tool.description ?? "";
      expect(description.length, tool.name).toBeLessThanOrEqual(UPFRONT_TEXT_LIMIT);
      expect(description.length, tool.name).toBeLessThanOrEqual(DEFERRED_TEXT_LIMIT);
      const summary = summaries.get(tool.name);
      if (summary !== undefined && tool.name !== "blender_run_python") expect(description.replace(/^DANGEROUS: /, "").startsWith(summary), tool.name).toBe(true);
    }
  });

  it("chooses the core set from the usage data, the benchmark and the workflows", () => {
    expect(CORE_RANKING).toEqual(derivedCoreRanking());
  });

  it("writes an example call for every tool that its schema accepts", () => {
    const check = new ArgumentCheck(new Map(all.map((tool) => [tool.name, tool.inputSchema])));
    for (const tool of all) expect(check.problems(tool.name, sampleObject(tool.inputSchema as Record<string, unknown>)), tool.name).toEqual([]);
  });
});

describe("a found tool in both client modes, on the real bridge", workBudget(240_000), () => {
  let local: BenchServer;
  let client: BenchClient;

  beforeAll(withWorkBudget(120_000, async () => {
    local = await startBenchServer((headless) => startHeadlessSession(headless));
    client = await local.connect("routing-modes", { toolsets: { kind: "core", families: [] } });
  }));

  afterAll(async () => {
    await client?.close();
    await local?.close();
  });

  it("is found by intent, refused with bad arguments in both modes, and runs with good ones", async () => {
    const before = (await client.listing()).tools.map((tool) => tool.name);
    expect(before).not.toContain("blender_bevel");
    const found = texts(await client.call("blender_find_tools", { query: "round off the sharp edges", limit: 3 }));
    expect(found).toMatch(/1\. blender_bevel /);
    expect((await client.listing()).tools.map((tool) => tool.name)).toContain("blender_bevel");
    expect((await client.call("blender_add_primitive", { type: "cube", name: "Box", size: 1 })).isError).toBeFalsy();
    const viaCall = await client.call("blender_call", { tool: "blender_bevel", arguments: { name: "Box", width: "wide" } });
    expect(texts(viaCall)).toMatch(/^bad_args: blender_bevel refused these arguments: width/);
    const direct = await client.call("blender_bevel", { name: "Box", width: 0.01, colour: "red" });
    expect(direct.isError).toBe(true);
    expect(texts(direct)).toMatch(/^bad_args: .*colour/);
    const done = await client.call("blender_call", { tool: "blender_bevel", arguments: { name: "Box", width: 0.01 } });
    expect(done.isError, texts(done)).toBeFalsy();
    const again = await client.call("blender_bevel", { name: "Box", width: 0.005 });
    expect(again.isError, texts(again)).toBeFalsy();
  });
});
