import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { CLOSEUP_NAMES, closeups } from "../src/judge/closeups.js";
import { judge } from "../src/judge/run.js";
import { freshDir } from "./judge/helpers.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const SESSION = join("bridge", "session.py");
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const NEW_TOOLS = [
  "blender_lathe",
  "blender_sweep",
  "blender_loft",
  "blender_extrude_outline",
  "blender_gear",
  "blender_sprocket",
  "blender_roller_chain",
  "blender_instances",
  "blender_rivet_line",
  "blender_add_modifier",
  "blender_mesh_query",
  "blender_transform_selection",
  "blender_displace_noise",
];
const PROP_SPEC = {
  name: "flanged pipe with a valve wheel",
  format: "glb",
  triangles: { max: 6000 },
  size: { x: [0.4, 0.44], y: [0.21, 0.23], z: [0.41, 0.45] },
  manifold: true,
  materials: { min: 1, max: 2 },
  uv: { required: true, maxOverlap: 0.05 },
  objects: { max: 1 },
  fileSize: { maxBytes: 2_000_000 },
  views: ["front", "three-quarter"],
  brief: "A brass pipe with a bolted flange at each end and a spoked valve wheel on top.",
};

function rimProfile(): number[][] {
  return Array.from({ length: 12 }, (_, index) => {
    const angle = (2 * Math.PI * index) / 12;
    return [0.055 + 0.007 * Math.cos(angle), 0.007 * Math.sin(angle)];
  });
}

describe.skipIf(!existsSync(SESSION))("a detailed prop built with the modelling tools only", workBudget(900_000), () => {
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
    client = new Client({ name: "modeling-kit", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function tool(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
    const result = (await client.callTool({ name: `blender_${name}`, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}\n${stderr}`);
    return result;
  }

  it("offers the modelling tools, guidance for them, and no run_python", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((entry) => entry.name);
    expect(names).toEqual(expect.arrayContaining(NEW_TOOLS));
    expect(names).not.toContain("blender_run_python");
    const modifier = tools.find((entry) => entry.name === "blender_add_modifier");
    expect(Object.keys((modifier?.inputSchema.properties ?? {}) as object)).toEqual(
      expect.arrayContaining(["displace", "weld", "screw", "curve", "simple_deform", "wireframe", "lattice", "shrinkwrap", "triangulate", "weighted_normal", "bevel", "solidify"]),
    );
    const instructions = client.getInstructions() ?? "";
    for (const word of ["blender_sweep", "blender_lathe", "blender_extrude_outline", "blender_gear", "blender_instances", "blender_boolean"]) {
      expect(instructions).toContain(word);
    }
  });

  it("builds, checks, exports and judges a flanged pipe with a valve wheel and a bolt ring, then renders close-ups", async () => {
    await tool("sweep", {
      name: "Pipe",
      preset: "circle",
      radius: 0.04,
      segments: 24,
      waypoints: [[0, 0, 0], [0, 0, 0.3], [0.3, 0, 0.3]],
      fillet_radius: 0.1,
      fillet_segments: 10,
    });
    await tool("lathe", { name: "BaseFlange", profile: [[0.035, -0.01], [0.11, -0.01], [0.11, 0.01], [0.035, 0.01]], closed: true, segments: 48 });
    await tool("lathe", { name: "BoltHead", profile: [[0, 0], [0.012, 0], [0.012, 0.009], [0.009, 0.012], [0, 0.012]], segments: 6 });
    const bolts = JSON.parse(
      texts(await tool("instances", { source: "BoltHead", name: "BoltRing", circle: { centre: [0, 0, 0.01], radius: 0.085, count: 8 }, align: "radial", realize: true })),
    ) as { count: number; realized: boolean; mesh: { vertices: number } };
    expect(bolts).toMatchObject({ count: 8, realized: true });
    await tool("delete", { names: ["BoltHead"] });
    await tool("lathe", {
      name: "TopFlange",
      profile: [[-0.01, 0.035], [-0.01, 0.09], [0.01, 0.09], [0.01, 0.035]],
      closed: true,
      axis: "x",
      segments: 48,
      location: [0.3, 0, 0.3],
    });
    await tool("lathe", { name: "Stem", profile: [[0, 0], [0.012, 0], [0.012, 0.075], [0.008, 0.08], [0, 0.08]], segments: 16, location: [0.2, 0, 0.33] });
    await tool("lathe", { name: "Rim", profile: rimProfile(), closed: true, segments: 40, location: [0.2, 0, 0.41] });
    await tool("lathe", { name: "Hub", profile: [[0, -0.01], [0.015, -0.01], [0.015, 0.01], [0, 0.01]], segments: 16, location: [0.2, 0, 0.41] });
    await tool("lathe", { name: "Spoke", profile: [[0, 0], [0.004, 0], [0.004, 0.05], [0, 0.05]], segments: 8 });
    await tool("instances", {
      source: "Spoke",
      name: "Spokes",
      circle: { centre: [0.2, 0, 0.41], radius: 0.005, count: 5 },
      align: "radial",
      rotation: [0, 90, 0],
      realize: true,
    });
    await tool("delete", { names: ["Spoke"] });
    await tool("join", { names: ["Pipe", "BaseFlange", "BoltRing", "TopFlange", "Stem", "Rim", "Hub", "Spokes"] });
    await tool("rename", { name: "Pipe", new_name: "ValvePipe" });
    await tool("add_material", { name: "Brass", base_color: [0.75, 0.55, 0.2], metallic: 0.9, roughness: 0.35 });
    await tool("assign_material", { name: "ValvePipe", material: "Brass" });
    await tool("uv_pack", { names: ["ValvePipe"] });

    const info = JSON.parse(texts(await tool("scene_info", {}))) as { objects: { name: string; dimensions: number[]; mesh: { triangles: number } }[] };
    expect(info.objects.map((entry) => entry.name)).toEqual(["ValvePipe"]);
    expect(info.objects[0]?.dimensions).toEqual([0.42, 0.22, 0.43]);
    expect(info.objects[0]?.mesh.triangles).toBeGreaterThan(2000);
    expect(info.objects[0]?.mesh.triangles).toBeLessThan(4000);

    const preview = await tool("render_preview", { views: ["three-quarter"], resolution: 256, samples: 4 });
    const image = preview.content.find((item) => item.type === "image");
    expect(image?.type === "image" ? Buffer.from(image.data, "base64").subarray(0, 8) : null).toEqual(PNG_SIGNATURE);

    await tool("export", { path: "prop.glb" });
    const asset = join(workspace, "prop.glb");
    expect(readFileSync(asset).subarray(0, 4).toString("ascii")).toBe("glTF");

    await client.close();

    const out = freshDir("modeling-kit");
    const specPath = join(out, "prop.spec.json");
    writeFileSync(specPath, JSON.stringify(PROP_SPEC, null, 2));
    const report = await judge({ specPath, assetPath: asset, outDir: join(out, "judge"), device: "cpu" });
    expect(report.rules.filter((rule) => !rule.pass).map((rule) => `${rule.rule}: ${JSON.stringify(rule.measured)}`)).toEqual([]);
    expect(report.passed).toBe(true);
    expect(report.measurements?.manifold).toMatchObject({ nonManifoldEdges: 0, boundaryEdges: 0, looseVertices: 0 });
    expect(report.measurements?.uv).toMatchObject({ present: true, overlap: 0 });

    const result = await closeups({ assetPath: asset, outDir: join(out, "closeups"), resolution: 256, samples: 8, device: "cpu" });
    expect(result.images.map((entry) => entry.name)).toEqual(CLOSEUP_NAMES);
    for (const entry of result.images) expect(statSync(entry.path).size, entry.name).toBeGreaterThan(2000);
    expect(readFileSync(result.sheet).subarray(0, 8)).toEqual(PNG_SIGNATURE);
  });
});
