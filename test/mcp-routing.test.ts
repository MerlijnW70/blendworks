import { join } from "node:path";
import { ToolListChangedNotificationSchema } from "@modelcontextprotocol/sdk/types.js";
import { afterEach, describe, expect, it } from "vitest";
import { serverInstructions, UPFRONT_TEXT_LIMIT } from "../src/mcp/instructions.js";
import { parseOptions } from "../src/mcp/options.js";
import { ALWAYS_LOAD_META, parseToolsets, resolveToolsets } from "../src/mcp/routing/disclosure.js";
import { toolNameOf } from "../src/mcp/routing/names.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";
import { call, type Harness, headlessHarness, scratchDir, texts } from "./mcp-helpers.js";

let harness: Harness | undefined;

afterEach(async () => {
  await harness?.close();
  harness = undefined;
});

async function names(current: Harness): Promise<string[]> {
  return (await current.client.listTools()).tools.map((tool) => tool.name).sort();
}

describe("--toolsets", () => {
  it("parses all, auto, core and core plus families, and refuses mixtures", () => {
    expect(parseToolsets("all")).toEqual({ kind: "all" });
    expect(parseToolsets("auto")).toEqual({ kind: "auto" });
    expect(parseToolsets("core")).toEqual({ kind: "core", families: [] });
    expect(parseToolsets("core,uv,materials")).toEqual({ kind: "core", families: ["uv", "materials"] });
    expect(parseToolsets("uv")).toEqual({ kind: "core", families: ["uv"] });
    expect(() => parseToolsets("all,uv")).toThrow(/stand alone/);
    expect(() => parseToolsets("UV!")).toThrow(/not a family name/);
    expect(parseOptions([]).toolsets).toEqual({ kind: "auto" });
    expect(parseOptions(["--toolsets", "core,uv"]).toolsets).toEqual({ kind: "core", families: ["uv"] });
  });

  it("defaults to the full listing only for a client that searches deferred tools itself", () => {
    expect(resolveToolsets({ kind: "auto" }, "claude-code").kind).toBe("all");
    expect(resolveToolsets({ kind: "auto" }, "cursor-vscode").kind).toBe("core");
    expect(resolveToolsets({ kind: "auto" }, undefined).kind).toBe("core");
    expect(resolveToolsets({ kind: "core", families: [] }, "claude-code").kind).toBe("core");
  });

  it("lists the core set, the search tool and the call tool by default, and every tool with all", async () => {
    harness = await headlessHarness();
    expect(await names(harness)).toEqual(["blender_add_primitive", "blender_call", "blender_export", "blender_find_tools", "blender_render_preview", "blender_scene_info"]);
    await harness.close();
    harness = await headlessHarness({}, { toolsets: { kind: "all" } });
    const all = await harness.client.listTools();
    expect(all.tools.map((tool) => tool.name)).toEqual(expect.arrayContaining(["blender_slow", "blender_find_tools", "library_search"]));
    expect(all.tools.map((tool) => tool.name)).not.toContain("blender_call");
    expect(all.tools.find((tool) => tool.name === "blender_export")?._meta).toEqual({ [ALWAYS_LOAD_META]: true });
    expect(all.tools.find((tool) => tool.name === "blender_slow")?._meta).toBeUndefined();
  });

  it("refuses a family the bridge does not declare", async () => {
    await expect(headlessHarness({}, { toolsets: { kind: "core", families: ["no_such_family"] } })).rejects.toThrow(/unknown families no_such_family/);
  });
});

describe("a tool found through blender_find_tools", () => {
  it("comes with its schema and an example, joins the listing, and the client hears tools/list_changed", async () => {
    harness = await headlessHarness();
    let changed = 0;
    harness.client.setNotificationHandler(ToolListChangedNotificationSchema, () => {
      changed += 1;
    });
    expect(await names(harness)).not.toContain("blender_slow");
    const found = texts(await call(harness.client, "blender_find_tools", { query: "wait before replying", limit: 1 }));
    expect(found).toContain("1. blender_slow");
    expect(found).toContain('Example: blender_slow {}');
    expect(found).toContain('"ms":{"type":"integer"');
    await expect.poll(() => changed).toBe(1);
    expect(await names(harness)).toContain("blender_slow");
  });

  it("is callable through blender_call, which checks the arguments against the real schema before Blender sees them", async () => {
    harness = await headlessHarness();
    const refused = await call(harness.client, "blender_call", { tool: "blender_slow", arguments: { ms: -5 } });
    expect(refused.isError).toBe(true);
    expect(texts(refused)).toMatch(/^bad_args: blender_slow refused these arguments: ms: .*>=0/);
    expect(texts(refused)).toContain('Its schema: {"type":"object"');
    const unknownField = await call(harness.client, "blender_call", { tool: "slow", arguments: { seconds: 1 } });
    expect(texts(unknownField)).toMatch(/seconds/);
    expect(harness.bridge.requests.map((request) => request.cmd)).not.toContain("slow");
    const done = await call(harness.client, "blender_call", { tool: "slow", arguments: { ms: 1 } });
    expect(done.isError).toBeFalsy();
    expect(harness.bridge.requests.at(-1)).toMatchObject({ cmd: "slow", args: { ms: 1 } });
  });

  it("is callable directly by name in a client that refreshes its list, with the same schema check while unlisted", async () => {
    harness = await headlessHarness();
    const refused = await call(harness.client, "blender_slow", { ms: "soon" });
    expect(texts(refused)).toMatch(/^bad_args: blender_slow refused these arguments: ms:/);
    expect(harness.bridge.requests.map((request) => request.cmd)).not.toContain("slow");
    expect((await call(harness.client, "blender_slow", { ms: 2 })).isError).toBeFalsy();
    expect(await names(harness)).toContain("blender_slow");
  });

  it("refuses an unknown tool with suggestions, and calling the router tools through blender_call", async () => {
    expect(toolNameOf("blender_library_search")).toBe("library_search");
    expect(toolNameOf("bevel")).toBe("blender_bevel");
    harness = await headlessHarness();
    expect(texts(await call(harness.client, "blender_call", { tool: "blender_exprt", arguments: {} }))).toMatch(/Unknown tool blender_exprt/);
    expect(texts(await call(harness.client, "blender_call", { tool: "blender_find_tools", arguments: { query: "x" } }))).toMatch(/directly/);
    expect(texts(await call(harness.client, "blender_find_tools", {}))).toMatch(/give a query, a goal, or both/);
    expect(texts(await call(harness.client, "blender_find_tools", { query: "x", families: ["nope"] }))).toMatch(/unknown families nope/);
  });
});

describe("search filters and nesting", () => {
  it("still shows a better match from outside the families the agent guessed", async () => {
    harness = await headlessHarness();
    const found = texts(await call(harness.client, "blender_find_tools", { query: "wait before replying", families: ["library"], limit: 2 }));
    expect(found).toMatch(/Better matches outside library:\n1\. blender_slow /);
    const inside = texts(await call(harness.client, "blender_find_tools", { query: "wait before replying", families: ["unsorted"], limit: 2 }));
    expect(inside).not.toContain("Better matches outside");
  });

  it("unwraps a blender_call nested in blender_call", async () => {
    harness = await headlessHarness();
    const nested = await call(harness.client, "blender_call", { tool: "blender_call", arguments: { tool: "slow", arguments: { ms: 1 } } });
    expect(nested.isError).toBeFalsy();
    expect(harness.bridge.requests.at(-1)).toMatchObject({ cmd: "slow", args: { ms: 1 } });
  });
});

describe("run_python in search results", () => {
  it("ranks below the built-in tools that match, and comes with more of them when shown", async () => {
    harness = await headlessHarness({ allowPython: true });
    const ranked = texts(await call(harness.client, "blender_find_tools", { query: "run python code to wait before replying or render a preview", limit: 3 }));
    expect(ranked).toMatch(/^Tools for .*\n1\. blender_slow /m);
    expect(ranked).toMatch(/\n3\. blender_run_python /);
    expect(ranked).toContain("blender_run_python is the last resort. Built-in tools that may do this without code:");
    const plain = texts(await call(harness.client, "blender_find_tools", { query: "wait before replying", limit: 1 }));
    expect(plain).not.toContain("last resort");
  });
});

describe("workflow goals", () => {
  it("are named in the server instructions and served whole by blender_find_tools, from one list", async () => {
    harness = await headlessHarness();
    const instructions = harness.client.getInstructions() ?? "";
    for (const workflow of WORKFLOWS) expect(instructions).toContain(workflow.goal.toLowerCase());
    for (const workflow of WORKFLOWS) {
      const served = texts(await call(harness.client, "blender_find_tools", { goal: workflow.goal }));
      expect(served, workflow.id).toContain(`Workflow "${workflow.goal}": ${workflow.steps.join(" > ")}.\n${workflow.note}`);
    }
    const dial = texts(await call(harness.client, "blender_find_tools", { goal: "engraved brass dial" }));
    expect(dial).toContain('Workflow "Engraved brass dial"');
    const rocks = texts(await call(harness.client, "blender_find_tools", { goal: "rock set" }));
    expect(rocks).toContain('Workflow "Rock set"');
  });
});

describe("server instructions", () => {
  it("fit Claude Code's 4,096-character cut with a 200-character workspace path, critical rules first", async () => {
    const folder = scratchDir();
    const workspace = join(folder, "w".repeat(Math.max(1, 200 - folder.length - 1)));
    harness = await headlessHarness({}, { workspace });
    const sent = harness.client.getInstructions() ?? "";
    expect(sent).toBe(serverInstructions(harness.started.workspace.root));
    expect(harness.started.workspace.root.length).toBeGreaterThanOrEqual(200);
    expect(sent.length).toBeLessThanOrEqual(UPFRONT_TEXT_LIMIT);
    const lines = sent.split("\n");
    expect(lines[1]).toContain(harness.started.workspace.root);
    expect(lines[2]).toContain("metres");
    expect(lines[3]).toContain("blender_find_tools");
  });
});
