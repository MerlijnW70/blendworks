import { existsSync } from "node:fs";
import type { Server } from "node:net";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";
import { FakeBridge, PNG_1X1 } from "./mcp-fake-bridge.js";
import { scratchDir } from "./mcp-helpers.js";

let client: Client | undefined;
let server: Server | undefined;

afterEach(async () => {
  await client?.close();
  client = undefined;
  if (server !== undefined) await new Promise((resolve) => server?.close(resolve));
  server = undefined;
});

function env(port: number): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) if (value !== undefined) out[key] = value;
  out["BLENDWORKS_PORT"] = String(port);
  return out;
}

describe("node src/mcp/index.ts over stdio", () => {
  it("serves the desktop bridge's tools, creating the workspace", async () => {
    const bridge = new FakeBridge();
    const listening = await bridge.listen();
    server = listening.server;
    const workspace = join(scratchDir(), "new-workspace");
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: ["--import", "tsx", join("src", "mcp", "index.ts"), "--workspace", workspace],
      env: env(listening.port),
      stderr: "pipe",
    });
    client = new Client({ name: "stdio-test", version: "0.0.0" });
    await client.connect(transport);
    expect(existsSync(workspace)).toBe(true);
    expect(client.getInstructions()).toContain("metres");
    const { tools } = await client.listTools();
    expect(tools.map((tool) => tool.name)).toContain("blender_render_preview");
    const preview = await client.callTool({ name: "blender_render_preview", arguments: { views: ["front"] } });
    expect(preview.content).toContainEqual({ type: "image", data: PNG_1X1, mimeType: "image/png" });
    const refused = await client.callTool({ name: "blender_export", arguments: { path: "../../escape.glb" } });
    expect(refused.isError).toBe(true);
  });
});
