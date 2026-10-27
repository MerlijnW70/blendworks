import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const SESSION = join("bridge", "session.py");
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const bridgeMissing = !existsSync(SESSION);

const TITLE = bridgeMissing
  ? "the MCP server with a real headless Blender session (skipped: bridge/session.py does not exist yet)"
  : "the MCP server with a real headless Blender session";

describe.skipIf(bridgeMissing)(TITLE, () => {
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
    client = new Client({ name: "e2e", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function tool(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
    const result = (await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}\n${stderr}`);
    return result;
  }

  it("lists the tools, builds a cube, renders a preview and exports a .glb into the workspace", workBudget(300_000), async () => {
    const { tools } = await client.listTools();
    const names = tools.map((entry) => entry.name);
    expect(names).toEqual(expect.arrayContaining(["blender_add_primitive", "blender_scene_info", "blender_render_preview", "blender_export"]));
    expect(names).not.toContain("blender_run_python");
    const library = ["library_search", "library_preview", "library_download", "library_apply"];
    expect(names.filter((name) => name.startsWith("library_"))).toEqual(library);
    expect(names.filter((name) => !library.includes(name)).every((name) => name.startsWith("blender_"))).toBe(true);

    await tool("blender_add_primitive", { type: "cube", size: 1 });
    const info = JSON.parse(texts(await tool("blender_scene_info", {}))) as unknown;
    expect(JSON.stringify(info)).toContain('"triangles":12');

    const preview = await tool("blender_render_preview", { views: ["front", "three-quarter"], resolution: 128, samples: 4 });
    const images = preview.content.filter((item) => item.type === "image");
    expect(images).toHaveLength(2);
    for (const image of images) {
      expect(image.mimeType).toBe("image/png");
      const png = Buffer.from(image.data, "base64");
      expect(png.subarray(0, 8)).toEqual(PNG_SIGNATURE);
      expect(png.readUInt32BE(16)).toBe(128);
      expect(png.readUInt32BE(20)).toBe(128);
    }
    expect(texts(preview)).toMatch(/^Rendered 2 views at 128x128 px with cycles on (cpu|gpu [A-Z]+ \(.+\)).*, 4 samples: front, three-quarter\.$/);

    await tool("blender_export", { path: "crate.glb" });
    const glb = readFileSync(join(workspace, "crate.glb"));
    expect(glb.subarray(0, 4).toString("ascii")).toBe("glTF");
    expect(glb.readUInt32LE(8)).toBe(glb.length);

    const escaped = (await client.callTool({ name: "blender_export", arguments: { path: "../escape.glb" } })) as CallToolResult;
    expect(escaped.isError).toBe(true);
    expect(existsSync(join(workspace, "..", "escape.glb"))).toBe(false);
  });
});
