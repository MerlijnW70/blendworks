import { readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const RING_RADIUS = 0.1;
const RING_WIDTH = 0.012;
const RING_HEIGHT = 0.02;
const RING_CENTRE_Z = 0.04;
const BAND_RADIUS = RING_RADIUS + RING_WIDTH / 2;

type Json = Record<string, unknown>;

const socket = (name: string, value: Json): Json => ({ socket: name, ...value });
const setting = (name: string, value: Json): Json => ({ name, ...value });
const link = (from: string, fromSocket: string, to: string, toSocket: string): Json => ({ from_node: from, from_socket: fromSocket, to_node: to, to_socket: toSocket });

const SLATE_GRAPH = {
  name: "Slate",
  nodes: [
    { name: "Coordinates", type: "texture_coordinate" },
    { name: "Cells", type: "voronoi_texture", inputs: [socket("Scale", { number: 14 })], settings: [setting("feature", { text: "DISTANCE_TO_EDGE" })] },
    { name: "Grain", type: "noise_texture", inputs: [socket("Scale", { number: 60 }), socket("Detail", { number: 6 })] },
    { name: "Edges", type: "map_range", inputs: [socket("From Max", { number: 0.12 })] },
    {
      name: "Tones",
      type: "color_ramp",
      stops: [
        { position: 0.0, color: [0.02, 0.025, 0.03] },
        { position: 0.55, color: [0.07, 0.085, 0.1] },
        { position: 1.0, color: [0.22, 0.24, 0.26] },
      ],
    },
    { name: "Relief", type: "bump", inputs: [socket("Strength", { number: 0.6 }), socket("Distance", { number: 0.004 })] },
    { name: "Shader", type: "principled_bsdf", inputs: [socket("Roughness", { number: 0.55 })] },
    { name: "Output", type: "material_output" },
  ],
  links: [
    link("Coordinates", "Object", "Cells", "Vector"),
    link("Coordinates", "Object", "Grain", "Vector"),
    link("Cells", "Distance", "Edges", "Value"),
    link("Edges", "Result", "Tones", "Fac"),
    link("Grain", "Fac", "Relief", "Height"),
    link("Tones", "Color", "Shader", "Base Color"),
    link("Relief", "Normal", "Shader", "Normal"),
    link("Shader", "BSDF", "Output", "Surface"),
  ],
};

const clean = (value: number): number => Math.round(value * 1e6) / 1e6 + 0;

function glbNodes(path: string): Map<string, { children: string[]; translation: number[] }> {
  const data = readFileSync(path);
  const length = data.readUInt32LE(12);
  const nodes = (JSON.parse(data.subarray(20, 20 + length).toString("utf8")) as { nodes: { name: string; children?: number[]; translation?: number[] }[] }).nodes;
  return new Map(nodes.map((node) => [node.name, { children: (node.children ?? []).map((index) => nodes[index]?.name ?? "").sort(), translation: node.translation ?? [0, 0, 0] }]));
}

describe("custom node graphs, hierarchy and brass through MCP tools only", workBudget(900_000), () => {
  const workspace = join(scratchDir(), "workspace");
  const out = freshDir("bridge-extras");
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
    client = new Client({ name: "bridge-extras", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function raw(name: string, args: Json): Promise<CallToolResult> {
    return (await client.callTool({ name: `blender_${name}`, arguments: args }, undefined, { timeout: 600_000 })) as CallToolResult;
  }

  async function call(name: string, args: Json): Promise<CallToolResult> {
    const result = await raw(name, args);
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}\n${stderr}`);
    return result;
  }

  async function tool(name: string, args: Json): Promise<Json> {
    return JSON.parse(texts(await call(name, args))) as Json;
  }

  function savePicture(result: CallToolResult, path: string): void {
    const image = result.content.find((item) => item.type === "image");
    if (image?.type !== "image") throw new Error("the render returned no image");
    writeFileSync(path, Buffer.from(image.data, "base64"));
    expect(readFileSync(path).subarray(0, 8)).toEqual(PNG_SIGNATURE);
    expect(statSync(path).size).toBeGreaterThan(5000);
  }

  it("offers the new tools, documents them, and still has no run_python", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((entry) => entry.name);
    expect(names).toEqual(expect.arrayContaining(["blender_material_nodes", "blender_material_info", "blender_add_empty", "blender_collection_create", "blender_collection_link", "blender_collection_unlink"]));
    expect(names).not.toContain("blender_run_python");
    const nodes = tools.find((entry) => entry.name === "blender_material_nodes");
    const types = (((nodes?.inputSchema.properties?.["nodes"] as Json)["items"] as Json)["properties"] as Json)["type"] as Json;
    expect(types["enum"]).toEqual(expect.arrayContaining(["principled_bsdf", "noise_texture", "voronoi_texture", "wave_texture", "color_ramp", "mix", "math", "vector_math", "mapping", "texture_coordinate", "bump", "normal_map", "geometry", "ambient_occlusion"]));
    expect(JSON.stringify(types["enum"])).not.toMatch(/script|group/i);
    const instructions = client.getInstructions() ?? "";
    for (const word of ["blender_material_nodes", "blender_material_info", "blender_add_empty", "blender_collection_link", "brass", "around_z"]) expect(instructions).toContain(word);
  });

  it("refuses a script node and a cycle, and leaves the scene as it was", async () => {
    const before = await tool("scene_info", { detail: "summary" });
    const script = await raw("material_nodes", { name: "Bad", nodes: [{ name: "Code", type: "script" }, { name: "Output", type: "material_output" }] });
    expect(script.isError).toBe(true);
    const cycle = await raw("material_nodes", {
      name: "Bad",
      nodes: [{ name: "A", type: "math" }, { name: "B", type: "math" }, { name: "Shader", type: "principled_bsdf" }, { name: "Output", type: "material_output" }],
      links: [link("A", "Value", "B", "Value"), link("B", "Value", "A", "Value"), link("Shader", "BSDF", "Output", "Surface")],
    });
    expect(cycle.isError).toBe(true);
    expect(texts(cycle)).toContain("cycle");
    expect(await tool("scene_info", { detail: "summary" })).toEqual(before);
  });

  it("builds an aged brass band and a custom node-graph material, and renders both", async () => {
    await tool("sweep", {
      name: "Ring",
      preset: "rounded_rectangle",
      width: RING_WIDTH,
      height: RING_HEIGHT,
      corner_radius: 0.001,
      segments: 3,
      circle: { centre: [0, 0, RING_CENTRE_Z], radius: RING_RADIUS, tolerance: 0.0001 },
    });
    await tool("material_procedural", { name: "Brass", brass: { patina: 0.35, polish: 0.45, scratch_direction: "around_z", scratch_scale: 1.0, bump: 0.05 } });
    await tool("assign_material", { name: "Ring", material: "Brass" });
    const angle = (15 * Math.PI) / 180;
    const band = await call("render_preview", {
      focus: { point: [BAND_RADIUS * Math.cos(angle), BAND_RADIUS * Math.sin(angle), RING_CENTRE_Z], direction: [Math.cos(angle), Math.sin(angle), 0.08], width: 0.045 },
      resolution: 320,
      samples: 8,
    });
    savePicture(band, join(out, "brass-band.png"));

    const built = await tool("material_nodes", SLATE_GRAPH);
    expect(built).toMatchObject({ name: "Slate", created: true, nodes: 8, links: 8 });
    await tool("add_primitive", { name: "Tile", type: "cube", size: 0.2, location: [0.5, 0, 0.1] });
    await tool("bevel", { name: "Tile", width: 0.01, segments: 2 });
    await tool("assign_material", { name: "Tile", material: "Slate" });
    await tool("material_layer", { material: "Slate", brass: { polish: 0.2 }, mask: "edges", amount: 0.6, distance: 0.02 });
    const slate = await call("render_preview", { focus: { object: "Tile", width: 0.4, direction: [0.6, -0.8, 0.7] }, resolution: 320, samples: 8 });
    savePicture(slate, join(out, "custom-graph.png"));
    const info = await tool("material_info", { name: "Slate" });
    expect(info["editable"]).toBe(true);
    expect((info["nodes"] as Json[]).map((node) => node["type"])).toEqual(expect.arrayContaining(["voronoi_texture", "noise_texture", "color_ramp", "bump", "principled_bsdf", "mix", "ambient_occlusion"]));
  });

  it("organises a cart with empties and collections, and exports its node tree", async () => {
    await tool("add_empty", { name: "Cart", display: "arrows", size: 0.4, location: [1, 0, 0] });
    await tool("add_empty", { name: "Wheels", parent: "Cart", location: [0, 1, 0] });
    await tool("add_primitive", { name: "WheelLeft", type: "cylinder", radius: 0.05, depth: 0.02, location: [0.3, 0, 0] });
    await tool("add_primitive", { name: "WheelRight", type: "cylinder", radius: 0.05, depth: 0.02, location: [-0.3, 0, 0] });
    await tool("parent", { name: "WheelLeft", parent: "Wheels", keep_transform: false });
    await tool("parent", { name: "WheelRight", parent: "Wheels", keep_transform: false });
    await tool("collection_create", { name: "Cart parts", objects: ["Cart", "Wheels", "WheelLeft", "WheelRight"] });
    await tool("collection_unlink", { collection: "Scene Collection", names: ["Cart", "Wheels", "WheelLeft", "WheelRight"] });
    const info = await tool("scene_info", { names: "W*" });
    const objects = Object.fromEntries((info["objects"] as Json[]).map((entry) => [entry["name"] as string, entry]));
    expect(objects["Wheels"]).toMatchObject({ parent: "Cart", collections: ["Cart parts"], display: "plain_axes" });
    expect(objects["WheelLeft"]).toMatchObject({ parent: "Wheels", collections: ["Cart parts"] });
    expect(info["collections"]).toEqual([{ name: "Cart parts", parent: "Scene Collection", objects: 4 }]);

    const exported = await tool("export", { path: "cart.glb", collection: "Cart parts" });
    expect(exported["objects"]).toEqual(["Cart", "WheelLeft", "WheelRight", "Wheels"]);
    const tree = glbNodes(join(workspace, "cart.glb"));
    expect(tree.get("Cart")?.children).toEqual(["Wheels"]);
    expect(tree.get("Wheels")?.children).toEqual(["WheelLeft", "WheelRight"]);
    expect(tree.get("Cart")?.translation.map(clean)).toEqual([1, 0, 0]);
    expect(tree.get("Wheels")?.translation.map(clean)).toEqual([0, 0, -1]);
  });
});
