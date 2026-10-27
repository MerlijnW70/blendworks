import { readFileSync } from "node:fs";
import { join } from "node:path";
import { deflateSync } from "node:zlib";
import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { BridgeConnection } from "../src/mcp/connection.js";
import { startHeadlessSession } from "../src/mcp/headless.js";
import { commandsFromDescribe } from "../src/mcp/schema.js";
import { createServer } from "../src/mcp/server.js";
import { libraryHarness, type LibraryHarness, serveBodies, textureUrl } from "./library-helpers.js";
import { call, connectClient, texts } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";

useBlenderSlot();

const CRC_TABLE = Array.from({ length: 256 }, (_, index) => {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  return value >>> 0;
});

function crc32(data: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of data) crc = (CRC_TABLE[(crc ^ byte) & 0xff] as number) ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(kind: string, data: Buffer): Buffer {
  const body = Buffer.concat([Buffer.from(kind, "ascii"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function solidPng(rgb: [number, number, number], size = 8): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 2, 0, 0, 0], 8);
  const row = Buffer.concat([Buffer.from([0]), ...Array.from({ length: size }, () => Buffer.from(rgb))]);
  const pixels = deflateSync(Buffer.concat(Array.from({ length: size }, () => row)));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", header), chunk("IDAT", pixels), chunk("IEND", Buffer.alloc(0))]);
}

const MAP_FILES: Record<string, Buffer> = {
  diff: solidPng([150, 140, 130]),
  nor_gl: solidPng([128, 128, 255]),
  nor_dx: solidPng([128, 64, 255]),
  rough: solidPng([200, 200, 200]),
  ao: solidPng([230, 230, 230]),
  disp: solidPng([128, 128, 128]),
  arm: solidPng([230, 200, 0]),
};

interface Step {
  command: string;
  result: Record<string, unknown>;
}

interface ApplyResult {
  steps: Step[];
  maps_not_wired?: string[];
}

describe("library_apply builds a real material_pbr material from a downloaded texture set", () => {
  let lib: LibraryHarness;
  let client: Client;
  let connection: BridgeConnection;

  beforeAll(async () => {
    lib = libraryHarness();
    connection = new BridgeConnection({ open: () => startHeadlessSession({ workspace: lib.workspace.root, allowPython: false }), owned: true, label: "headless Blender session" });
    await connection.connect();
    const commands = commandsFromDescribe((await connection.request("describe", {})).result);
    const server = createServer({ connection, workspace: lib.workspace, commands, library: lib.library });
    client = await connectClient({ server, connection, workspace: lib.workspace, commands, mode: "headless" });
    serveBodies(lib.polyHaven, "aerial_asphalt_01", new Map(Object.entries(MAP_FILES).map(([map, body]) => [textureUrl(map, "1k", "png"), body])));
  }, 120_000);

  afterAll(async () => {
    await client?.close();
    await connection?.close();
  });

  async function ok(name: string, args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const result = await call(client, name, args);
    expect(result.isError, texts(result)).toBeFalsy();
    return JSON.parse(texts(result)) as Record<string, unknown>;
  }

  async function download(maps?: string[]): Promise<void> {
    await ok("library_download", { id: "aerial_asphalt_01", resolution: "1k", format: "png", ...(maps === undefined ? {} : { maps }) });
  }

  it("wires the default maps with the right colour spaces and exports them", async () => {
    await download();
    await ok("blender_add_primitive", { type: "plane", name: "Floor", size: 2 });
    const applied = (await ok("library_apply", { id: "aerial_asphalt_01", object: "Floor", material: "Asphalt" })) as unknown as ApplyResult;
    expect(applied.steps.map((step) => step.command)).toEqual(["blender_material_pbr", "blender_assign_material"]);
    expect(applied.maps_not_wired).toBeUndefined();
    const built = applied.steps[0]?.result as { name: string; maps: Record<string, string>; colorspaces: Record<string, string> };
    expect(built.name).toBe("Asphalt");
    expect(Object.keys(built.maps).sort()).toEqual(["ao", "base_color", "height", "normal", "roughness"]);
    expect(built.colorspaces).toEqual({
      "aerial_asphalt_01_diff_1k.png": "sRGB",
      "aerial_asphalt_01_nor_gl_1k.png": "Non-Color",
      "aerial_asphalt_01_rough_1k.png": "Non-Color",
      "aerial_asphalt_01_ao_1k.png": "Non-Color",
      "aerial_asphalt_01_disp_1k.png": "Non-Color",
    });
    expect(applied.steps[1]?.result).toMatchObject({ name: "Floor", material: "Asphalt" });
    await ok("blender_export", { path: "floor.glb" });
    const data = readFileSync(join(lib.workspace.root, "floor.glb"));
    const document = JSON.parse(data.subarray(20, 20 + data.readUInt32LE(12)).toString("utf8")) as { materials: Record<string, Record<string, unknown>>[] };
    const material = document.materials[0] ?? {};
    expect(material["name"]).toBe("Asphalt");
    expect(material["pbrMetallicRoughness"]).toHaveProperty("baseColorTexture");
    expect(material["pbrMetallicRoughness"]).toHaveProperty("metallicRoughnessTexture");
    expect(material).toHaveProperty("normalTexture");
    expect(material).toHaveProperty("occlusionTexture");
  }, 300_000);

  it("flips a DirectX normal map and prefers separate roughness over the ARM map", async () => {
    await download(["Diffuse", "nor_dx", "Rough", "arm"]);
    const applied = (await ok("library_apply", { id: "aerial_asphalt_01", material: "DirectX" })) as unknown as ApplyResult;
    const built = applied.steps[0]?.result as { maps: Record<string, string> };
    expect(built.maps["normal"]).toBe("aerial_asphalt_01_nor_dx_1k.png_opengl");
    expect(built.maps["roughness"]).toBe("aerial_asphalt_01_rough_1k.png");
    expect(built.maps).not.toHaveProperty("orm");
    expect(applied.maps_not_wired).toEqual(["arm"]);
  }, 300_000);

  it("wires an ARM map as orm when it is the only data map", async () => {
    await download(["Diffuse", "arm"]);
    const applied = (await ok("library_apply", { id: "aerial_asphalt_01", material: "Packed" })) as unknown as ApplyResult;
    const built = applied.steps[0]?.result as { maps: Record<string, string>; colorspaces: Record<string, string> };
    expect(built.maps).toEqual({ base_color: "aerial_asphalt_01_diff_1k.png", orm: "aerial_asphalt_01_arm_1k.png" });
    expect(built.colorspaces["aerial_asphalt_01_arm_1k.png"]).toBe("Non-Color");
  }, 300_000);
});
