import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { BAKE_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, defaultTimeoutFor } from "../src/mcp/connection.js";
import { buildTools } from "../src/mcp/tools.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";

const TEXTURE_TOOLS = [
  "blender_image_load",
  "blender_image_new",
  "blender_image_save",
  "blender_image_info",
  "blender_material_pbr",
  "blender_material_procedural",
  "blender_material_layer",
  "blender_bake",
  "blender_uv_pack",
];

interface GlbMaterial {
  pbrMetallicRoughness: Record<string, unknown>;
  normalTexture?: unknown;
}

function glbDocument(path: string): { materials: GlbMaterial[]; images: unknown[] } {
  const data = readFileSync(path);
  expect(data.subarray(0, 4).toString("ascii")).toBe("glTF");
  const length = data.readUInt32LE(12);
  expect(data.subarray(16, 20).toString("ascii")).toBe("JSON");
  return JSON.parse(data.subarray(20, 20 + length).toString("utf8")) as { materials: GlbMaterial[]; images: unknown[] };
}

const MAX_BAKE_SECONDS = Number(/MAX_BAKE_SECONDS = ([\d.]+)/.exec(readFileSync(join("bridge", "blendworks_bridge", "limits.py"), "utf8"))?.[1]);

describe("texture tool limits and hints", () => {
  it("gives bake more time than its own cap and marks image_info read-only", () => {
    expect(MAX_BAKE_SECONDS).toBe(600);
    expect(defaultTimeoutFor("bake")).toBe(BAKE_TIMEOUT_MS);
    expect(BAKE_TIMEOUT_MS).toBeGreaterThanOrEqual(MAX_BAKE_SECONDS * 1000 + 30_000);
    expect(defaultTimeoutFor("image_save")).toBe(DEFAULT_TIMEOUT_MS);
    const schema = { type: "object" as const, properties: {}, additionalProperties: false };
    const tools = buildTools([
      { name: "image_info", description: "List images.", inputSchema: schema, pathFields: [], dangerous: false },
      { name: "bake", description: "Bake.", inputSchema: schema, pathFields: [], dangerous: false },
    ]);
    expect(tools.get("blender_image_info")?.tool.annotations).toMatchObject({ readOnlyHint: true, openWorldHint: false });
    expect(tools.get("blender_bake")?.tool.annotations).toMatchObject({ readOnlyHint: false });
  });
});

describe("texture, material and bake tools through the MCP server", () => {
  const workspace = join(scratchDir(), "workspace");
  let client: Client;
  let stderr = "";

  beforeAll(async () => {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value;
    env["BLENDWORKS_PORT"] = String(await unusedPort());
    env["BLENDER"] = blenderPath();
    env["BLENDWORKS_DEVICE"] = "cpu";
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: ["--import", "tsx", join("src", "mcp", "index.ts"), "--workspace", workspace],
      env,
      stderr: "pipe",
    });
    transport.stderr?.on("data", (chunk: Buffer) => {
      stderr = (stderr + chunk.toString()).slice(-4000);
    });
    client = new Client({ name: "textures", version: "0.0.0" });
    await client.connect(transport);
  }, 120_000);

  afterAll(async () => {
    await client?.close();
  });

  async function tool(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const result = (await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}\n${stderr}`);
    return JSON.parse(texts(result)) as Record<string, unknown>;
  }

  it("lists the texture tools and bakes a procedural cube into a textured .glb", async () => {
    const names = (await client.listTools()).tools.map((entry) => entry.name);
    expect(names).toEqual(expect.arrayContaining(TEXTURE_TOOLS));

    await tool("blender_add_primitive", { type: "cube", name: "Crate", size: 1 });
    await tool("blender_uv_smart_project", { name: "Crate", island_margin: 0.02 });
    await tool("blender_material_procedural", { name: "Planks", wood: { grain: "x", seed: 4 } });
    await tool("blender_material_layer", { material: "Planks", dirt: {}, mask: "cavity", amount: 0.4 });
    await tool("blender_assign_material", { name: "Crate", material: "Planks" });
    const baked = await tool("blender_bake", { names: ["Crate"], channels: ["base_color", "roughness", "normal"], size: 64, rewire: true });
    expect(baked["device"]).toMatchObject({ device: "cpu", backend: null });
    expect(baked["images"]).toEqual(["Crate_base_color", "Crate_roughness", "Crate_normal"]);
    expect(baked["material"]).toBe("Crate_baked");

    await tool("blender_export", { path: "crate.glb" });
    const document = glbDocument(join(workspace, "crate.glb"));
    const material = document.materials[0];
    expect(material?.pbrMetallicRoughness).toHaveProperty("baseColorTexture");
    expect(material?.pbrMetallicRoughness).toHaveProperty("metallicRoughnessTexture");
    expect(material).toHaveProperty("normalTexture");

    const saved = await tool("blender_image_save", { name: "Crate_base_color", path: "maps/base.png" });
    expect(saved).toMatchObject({ path: "maps/base.png", format: "png", source: "file" });
    expect(existsSync(join(workspace, "maps", "base.png"))).toBe(true);
    const rebuilt = await tool("blender_material_pbr", { name: "FromFile", base_color_path: "maps/base.png", normal: "Crate_normal" });
    expect(rebuilt["colorspaces"]).toEqual({ "Crate_base_color": "sRGB", "Crate_normal": "Non-Color" });

    const escaped = (await client.callTool({ name: "blender_image_load", arguments: { path: "../outside.png" } })) as CallToolResult;
    expect(escaped.isError).toBe(true);
    const unknown = (await client.callTool({ name: "blender_material_procedural", arguments: { name: "Bad", wood: { knots: 2 } } })) as CallToolResult;
    expect(unknown.isError).toBe(true);
    expect(texts(unknown)).toContain("knots");
  }, 300_000);
});
