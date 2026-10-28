import { copyFileSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { closeups } from "../src/judge/closeups.js";
import { judge } from "../src/judge/run.js";
import { freshDir } from "./judge/helpers.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const MIP_BYTES_1024 = 5_592_404;
const MIP_BYTES_512 = 1_398_100;
const CHANNELS = ["base_color", "roughness", "metallic", "normal"];
const RING_RADIUS = 0.1;
const RING_WIDTH = 0.012;
const RING_HEIGHT = 0.02;
const RING_CENTRE_Z = 0.04;
const BAND_RADIUS = RING_RADIUS + RING_WIDTH / 2;

const STRICT_SPEC = {
  name: "engraved brass ring on a veined marble plinth",
  format: "glb",
  faces: { maxDegenerate: 0 },
  gltf: { validator: { maxErrors: 0, maxWarnings: 0 } },
  textures: {
    required: ["baseColor", "metallicRoughness", "normal"],
    minSize: 512,
    maxSize: 1024,
    embedded: true,
    maxCount: 6,
    maxGpuBytes: 3 * (MIP_BYTES_1024 + MIP_BYTES_512),
    powerOfTwo: true,
  },
  parts: { maxFloating: 0 },
  renders: { required: true },
  views: ["three-quarter", "front", "top"],
  brief: "A brass ring with degree numbers every 30 degrees and two zodiac signs on a veined marble plinth.",
};

type Json = Record<string, unknown>;

describe("polish round 2 through MCP tools only", workBudget(1_800_000), () => {
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
    client = new Client({ name: "polish-2", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function call(name: string, args: Json): Promise<CallToolResult> {
    const result = (await client.callTool({ name: `blender_${name}`, arguments: args }, undefined, { timeout: 900_000 })) as CallToolResult;
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
  }

  it("offers the new tools and no run_python", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((entry) => entry.name);
    expect(names).toEqual(expect.arrayContaining(["blender_engrave", "blender_clean_mesh", "blender_sweep", "blender_uv_pack", "blender_bake", "blender_export"]));
    expect(names).not.toContain("blender_run_python");
    const instructions = client.getInstructions() ?? "";
    for (const word of ["blender_engrave", "blender_clean_mesh", "marble"]) expect(instructions).toContain(word);
    const texturing = texts((await client.callTool({ name: "blender_find_tools", arguments: { goal: "texture an asset" } })) as CallToolResult);
    for (const word of ["atlas_sizes", "min_island_area", "coverage"]) expect(texturing).toContain(word);
  });

  it("builds an engraved ring and a veined plinth, bakes per material, exports and passes a strict judge", async () => {
    const out = freshDir("polish-2");
    const ring = await tool("sweep", {
      name: "Ring",
      preset: "rounded_rectangle",
      width: RING_WIDTH,
      height: RING_HEIGHT,
      corner_radius: 0.001,
      segments: 3,
      circle: { centre: [0, 0, RING_CENTRE_Z], radius: RING_RADIUS, tolerance: 0.0001 },
    });
    expect(ring).toMatchObject({ closed: true, manifold: true });
    expect((ring["path"] as Json)["chord_error"] as number).toBeLessThanOrEqual(0.0001);
    await tool("lathe", { name: "Plinth", profile: [[0, 0], [0.14, 0], [0.14, 0.024], [0.134, 0.03], [0, 0.03]], segments: 96 });

    await tool("material_procedural", { name: "Brass", worn_metal: { color: [0.6, 0.38, 0.1], roughness: 0.32, wear: 0.3, scratch_scale: 2.0, bump: 0.02 } });
    await tool("material_procedural", { name: "Marble", marble: { scale: 7.0, seed: 4, turbulence: 0.6, vein_width: 0.16 } });
    await tool("assign_material", { name: "Ring", material: "Brass" });
    await tool("assign_material", { name: "Plinth", material: "Marble" });

    const band = (angle: number) => ({ radius: BAND_RADIUS, axis: [0, 0, 1], centre: [0, 0, RING_CENTRE_Z], angle });
    const degrees = await tool("engrave", {
      name: "Ring",
      text: "{n}",
      cylinder: band(0),
      size: 0.0075,
      depth: 0.0006,
      repeat: { count: 12, step: 30, number_start: 0, number_step: 30 },
      tolerance: 0.00005,
    });
    expect(degrees).toMatchObject({ mode: "cut", instances: 12, manifold: true });
    expect(degrees["volume_change"] as number).toBeLessThan(0);
    for (const [sign, angle] of [["aries", 15], ["leo", 195]] as const) {
      const symbol = await tool("engrave", { name: "Ring", text: `{${sign}}`, cylinder: band(angle), size: 0.009, depth: 0.0006, tolerance: 0.00005 });
      expect(symbol).toMatchObject({ manifold: true, instances: 1 });
    }

    for (const name of ["Ring", "Plinth"]) {
      const cleaned = await tool("clean_mesh", { name });
      expect(cleaned).toMatchObject({ manifold: true, degenerate_triangles_after: 0 });
    }

    const smart = await tool("uv_smart_project", { name: "Ring", island_margin: 0.002, min_island_area: 0.002 });
    expect((smart["islands"] as Json)["merged"] as number).toBeGreaterThan(0);
    await tool("uv_smart_project", { name: "Plinth", island_margin: 0.01 });
    const packed = await tool("uv_pack", { names: ["Ring", "Plinth"], target: "coverage", shared: false, margin: 0.004, texture_size: 1024, time_limit: 15 });
    expect(packed["target"]).toBe("coverage");
    expect(packed["coverage"] as number).toBeGreaterThan(0.2);
    expect((packed["texel_density"] as Json)["min"] as number).toBeGreaterThan(0);

    const marble = await call("render_preview", { focus: { object: "Plinth", width: 0.3, direction: [0.5, -0.8, 1.2] }, resolution: 320, samples: 8 });
    savePicture(marble, join(out, "marble-before-bake.png"));

    const baked = await tool("bake", {
      names: ["Ring", "Plinth"],
      channels: CHANNELS,
      size: 256,
      atlas_sizes: [{ materials: ["Brass"], size: 1024 }, { materials: ["Marble"], size: 512 }],
      prefix: "Polish",
      rewire: true,
      samples: { base_color: 4, roughness: 4, metallic: 4, normal: 8 },
    });
    expect(baked["materials"]).toEqual(["Brass_baked", "Marble_baked"]);
    const textures = baked["textures"] as { material: string; size: number[] }[];
    expect(textures.filter((entry) => entry.material === "Brass").map((entry) => entry.size)).toEqual(Array(4).fill([1024, 1024]));
    expect(textures.filter((entry) => entry.material === "Marble").map((entry) => entry.size)).toEqual(Array(4).fill([512, 512]));
    expect(baked["gpu_bytes"]).toBe(4 * MIP_BYTES_1024 + 4 * MIP_BYTES_512);

    const exported = await tool("export", { path: "polish-2.glb" });
    expect(exported["options"]).toMatchObject({ tangents: true, image_format: "auto", draco: false });
    const asset = join(workspace, "polish-2.glb");
    expect(readFileSync(asset).subarray(0, 4).toString("ascii")).toBe("glTF");
    copyFileSync(asset, join(out, "polish-2.glb"));

    const onBand = (degrees: number) => {
      const angle = (degrees * Math.PI) / 180;
      return { point: [BAND_RADIUS * Math.cos(angle), BAND_RADIUS * Math.sin(angle), RING_CENTRE_Z], direction: [Math.cos(angle), Math.sin(angle), 0.08] };
    };
    const numbers = await call("render_preview", { focus: { ...onBand(15), width: 0.075 }, resolution: 320, samples: 8 });
    savePicture(numbers, join(out, "ring-numbers-and-aries.png"));
    const leo = await call("render_preview", { focus: { ...onBand(195), width: 0.045 }, resolution: 320, samples: 8 });
    savePicture(leo, join(out, "ring-leo.png"));
    const veins = await call("render_preview", { focus: { point: [0.0, 0.065, 0.03], direction: [0.0, -0.15, 1.0], width: 0.12 }, resolution: 320, samples: 8 });
    savePicture(veins, join(out, "marble-veins-baked.png"));
    const plinth = await call("render_preview", { focus: { object: "Plinth", width: 0.34, direction: [0.5, -0.8, 1.2] }, resolution: 320, samples: 8 });
    savePicture(plinth, join(out, "marble-baked.png"));

    await client.close();

    const specPath = join(out, "polish-2.spec.json");
    writeFileSync(specPath, JSON.stringify(STRICT_SPEC, null, 2));
    const report = await judge({ specPath, assetPath: asset, outDir: join(out, "judge"), device: "auto" });
    expect(report.rules.filter((rule) => !rule.pass).map((rule) => `${rule.rule}: ${JSON.stringify(rule.measured)}`)).toEqual([]);
    expect(report.passed).toBe(true);
    const names = report.rules.map((rule) => rule.rule);
    expect(names).toEqual(expect.arrayContaining(["faces.maxDegenerate", "gltf.validator.maxErrors", "gltf.validator.maxWarnings", "textures.maxGpuBytes", "parts.maxFloating"]));

    const result = await closeups({ assetPath: asset, outDir: join(out, "closeups"), resolution: 300, samples: 4, device: "auto" });
    for (const entry of result.images) expect(statSync(entry.path).size, entry.name).toBeGreaterThan(2000);
    expect(readFileSync(result.sheet).subarray(0, 8)).toEqual(PNG_SIGNATURE);
  });
});
