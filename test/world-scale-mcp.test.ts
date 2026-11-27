import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult, Tool } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { commandsFromDescribe } from "../src/mcp/schema.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Problem = { call: number; argument: string; value?: unknown; message: string };
type Checked = { valid: boolean; problems: Problem[]; ran: number };

function openObjects(schema: unknown, path: string, found: string[]): string[] {
  if (typeof schema !== "object" || schema === null) return found;
  const record = schema as Record<string, unknown>;
  if (record["additionalProperties"] === true) found.push(path);
  const properties = (record["properties"] ?? {}) as Record<string, unknown>;
  for (const [name, field] of Object.entries(properties)) openObjects(field, `${path}.${name}`, found);
  if (record["items"] !== undefined) openObjects(record["items"], `${path}[]`, found);
  return found;
}

describe("strict schemas stay strict when converted", () => {
  it("keeps additionalProperties true only where the bridge schema says so", () => {
    const [strict, open] = commandsFromDescribe({
      commands: [
        { name: "transform", schema: { type: "object", properties: { name: { type: "string" } }, additionalProperties: false } },
        { name: "validate", schema: { type: "object", properties: { calls: { type: "array", items: { type: "object", properties: { args: { type: "object", properties: {}, additionalProperties: true } } } } } } },
      ],
    });
    expect(strict!.inputSchema["additionalProperties"]).toBe(false);
    expect(openObjects(open!.inputSchema, "validate", [])).toEqual(["validate.calls[].args"]);
  });
});

describe("validate and limits through the MCP server", () => {
  const workspace = join(scratchDir(), "workspace");
  let client: Client;
  let stderr = "";

  beforeAll(withWorkBudget(120_000, async () => {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value;
    env["BLENDWORKS_PORT"] = String(await unusedPort());
    env["BLENDER"] = blenderPath();
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: ["--import", "tsx", join("src", "mcp", "index.ts"), "--workspace", workspace, "--toolsets", "all"],
      env,
      stderr: "pipe",
    });
    transport.stderr?.on("data", (chunk: Buffer) => {
      stderr = (stderr + chunk.toString()).slice(-4000);
    });
    client = new Client({ name: "world-scale", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function raw(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
    return (await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
  }

  it("lists only validate's call arguments as open objects", workBudget(120_000), async () => {
    const { tools } = await client.listTools();
    const open = tools.flatMap((tool: Tool) => openObjects(tool.inputSchema, tool.name, []));
    expect(open).toEqual(["blender_validate.calls[].args"]);
  });

  it("still refuses an unknown field on a normal tool", workBudget(120_000), async () => {
    const result = await raw("blender_transform", { name: "x", bogus: 1 });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/bogus/);
  });

  it("gives the same problems as a script and runs nothing", workBudget(120_000), async () => {
    const calls = [
      { cmd: "add_primitive", args: { type: "cube", name: "a", location: [0, 0, 500_000] } },
      { cmd: "noise_displace", args: { name: "missing", amplitude: 50_000 } },
      { cmd: "add_primitive", args: { type: "cube", name: "a" } },
      { cmd: "atmosphere", args: { visibility: -5, colour: "blue" } },
      { cmd: "no_such_tool", args: {} },
    ];
    const result = await raw("blender_validate", { calls, from_scene: false });
    expect(result.isError, `${texts(result)}\n${stderr}`).toBeFalsy();
    const checked = JSON.parse(texts(result)) as Checked;
    expect(checked.valid).toBe(false);
    expect(checked.ran).toBe(0);
    const seen = new Set(checked.problems.map((problem) => `${problem.call} ${problem.argument}`));
    for (const expected of ["0 args.location[2]", "1 args.name", "1 args.amplitude", "2 args.name", "3 args.visibility", "3 args.colour", "4 cmd"]) expect(seen.has(expected), expected).toBe(true);
    const location = checked.problems.find((problem) => problem.argument === "args.location[2]")!;
    expect(location.value).toBe(500_000);
    expect(location.message).toMatch(/limit coordinate/);
  });
});
