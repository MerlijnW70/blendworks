import { existsSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult, Tool } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const SESSION = join("bridge", "session.py");

type Schema = { properties?: Record<string, Schema>; enum?: string[]; description?: string };

function field(tool: Tool | undefined, ...path: string[]): Schema | undefined {
  let schema = tool?.inputSchema as Schema | undefined;
  for (const key of path) schema = schema?.properties?.[key];
  return schema;
}

describe.skipIf(!existsSync(SESSION))("engraving, scales, solvers and aged materials over MCP", workBudget(300_000), () => {
  const workspace = join(scratchDir(), "workspace");
  let client: Client;
  let tools: Tool[] = [];
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
    client = new Client({ name: "engraving", version: "0.0.0" });
    await client.connect(transport);
    tools = (await client.listTools()).tools;
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function call(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const result = (await client.callTool({ name: `blender_${name}`, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}\n${stderr}`);
    return JSON.parse(texts(result)) as Record<string, unknown>;
  }

  const tool = (name: string) => tools.find((entry) => entry.name === `blender_${name}`);

  it("lists the new parameters in the tool schemas", () => {
    const scale = tool("engrave_scale");
    expect(Object.keys(field(scale)?.properties ?? {})).toEqual(expect.arrayContaining(["ring", "cylinder", "start", "end", "step", "count", "mirror", "classes", "depth", "height"]));
    expect(field(scale, "mirror")?.enum).toEqual(["none", "quadrants"]);
    expect(Object.keys(field(tool("engrave"), "ring")?.properties ?? {})).toEqual(expect.arrayContaining(["centre", "axis", "radius", "up", "angle"]));
    expect(field(tool("boolean"), "solver")?.enum).toContain("auto");
    expect(field(tool("sweep"), "closed")?.description).toContain("arc");
    expect(field(tool("material_procedural"), "brass", "age")?.enum).toEqual(["new", "handled", "aged", "dull"]);
    expect(Object.keys(field(tool("material_procedural"), "marble")?.properties ?? {})).toEqual(expect.arrayContaining(["vein_softness", "branching"]));
  });

  it("names only tools that exist in its instructions, and covers the new ones there or in the workflow notes", async () => {
    const instructions = client.getInstructions() ?? "";
    const names = new Set(tools.map((entry) => entry.name));
    const mentioned = [...instructions.matchAll(/blender_[a-z_]+/g)].map((match) => match[0]);
    const unlisted = new Set(["blender_call", "blender_run_python"]);
    expect(mentioned.filter((name) => !names.has(name) && !unlisted.has(name))).toEqual([]);
    for (const word of ["blender_engrave_scale", "ring"]) expect(instructions).toContain(word);
    const goals = ["engraved brass dial", "plates with holes", "realistic materials", "pipes and rings"];
    const notes = (await Promise.all(goals.map(async (goal) => texts((await client.callTool({ name: "blender_find_tools", arguments: { goal } })) as CallToolResult)))).join("\n");
    for (const word of ["blender_engrave_scale", "solver auto", "brass age", "vein_softness", "closed true"]) expect(notes).toContain(word);
  });

  it("engraves a dial with majors and numbers it, through the tools", async () => {
    await call("sweep", { name: "Dial", preset: "rounded_rectangle", width: 0.04, height: 0.006, corner_radius: 0.0008, segments: 2, circle: { radius: 0.1, tolerance: 0.0001 } });
    const scale = await call("engrave_scale", { name: "Dial", ring: { centre: [0, 0, 0.003], radius: 0.108 }, step: 5, depth: 0.0004, length: 0.004, width: 0.0005, classes: [{ every: 6, length: 0.008, depth: 0.0007 }] });
    expect(scale).toMatchObject({ marks: 72, manifold: true, classes: [{ every: 1, marks: 60 }, { every: 6, marks: 12 }] });
    expect((scale["quality"] as Record<string, number>)["slivers"]).toBe(0);
    const numbers = await call("engrave", { name: "Dial", text: "{n}", ring: { centre: [0, 0, 0.003], radius: 0.094 }, size: 0.005, depth: 0.0005, repeat: { count: 12, step: 30, number_start: 0, number_step: 30 } });
    expect(numbers).toMatchObject({ manifold: true, instances: 12, surface: "ring", solver: { used: "manifold" } });
  });
});
