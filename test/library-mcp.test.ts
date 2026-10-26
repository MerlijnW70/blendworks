import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { afterEach, describe, expect, it } from "vitest";
import { BridgeConnection } from "../src/mcp/connection.js";
import type { BridgeRequest } from "../src/mcp/protocol.js";
import { commandsFromDescribe } from "../src/mcp/schema.js";
import { createServer } from "../src/mcp/server.js";
import { FakeBridge } from "./mcp-fake-bridge.js";
import { barrelBodies, FIXTURES, HDRI_1K, libraryHarness, type LibraryHarness, serveBodies, textureUrl } from "./library-helpers.js";
import { call, connectClient, texts } from "./mcp-helpers.js";

type Spec = { description: string; schema: Record<string, unknown>; dangerous?: boolean };

function object(properties: Record<string, unknown>, required: string[] = []): Record<string, unknown> {
  return { type: "object", properties, required, additionalProperties: false };
}

const text = (description: string) => ({ type: "string", description, minLength: 1, maxLength: 1024 });

const LIBRARY_COMMANDS: Record<string, Spec> = {
  set_world_hdri: {
    description: "Light the scene with an equirectangular .hdr or .exr image from the workspace as the world environment.",
    schema: object({ path: text("Image path."), strength: { type: "number", minimum: 0, maximum: 100, default: 1 }, rotation: { type: "number", minimum: -360, maximum: 360, default: 0 } }, ["path"]),
  },
  import: { description: "Import a .glb, .gltf, .fbx or .obj file from the workspace into the scene.", schema: object({ path: text("File path."), select: { type: "boolean", default: true } }, ["path"]) },
  assign_material: { description: "Give an object a material.", schema: object({ name: text("Object."), material: text("Material name.") }, ["name", "material"]) },
};

const MAP_KEYS = ["base_color", "metallic", "roughness", "orm", "normal", "height", "emission", "alpha", "ao"];

const MATERIAL_PBR: Spec = {
  description: "Build a Principled BSDF material from PBR image maps with the right colour spaces, ready for glTF export.",
  schema: object(
    {
      name: text("Material name."),
      ...Object.fromEntries(MAP_KEYS.flatMap((key) => [[key, text(`Name of a loaded image for ${key}.`)], [`${key}_path`, text(`Workspace path of an image file for ${key}.`)]])),
      normal_convention: { type: "string", description: "Normal map convention.", enum: ["opengl", "directx"], default: "opengl" },
    },
    ["name"],
  ),
};

class LibraryBridge extends FakeBridge {
  constructor(private readonly extra: Record<string, Spec>) {
    super();
  }

  override commands(): Record<string, Spec> {
    return { ...super.commands(), ...LIBRARY_COMMANDS, ...this.extra };
  }

  override answer(request: BridgeRequest): Record<string, unknown> {
    if (request.cmd in LIBRARY_COMMANDS || request.cmd in this.extra) {
      const result = request.cmd === "material_pbr" ? { name: request.args["name"], created: true } : { echo: request.args };
      return { id: request.id, ok: true, result };
    }
    return super.answer(request);
  }

  sent(cmd: string): Record<string, unknown>[] {
    return this.requests.filter((request) => request.cmd === cmd).map((request) => request.args);
  }
}

interface Setup {
  client: Client;
  bridge: LibraryBridge;
  lib: LibraryHarness;
  close: () => Promise<void>;
}

let setup: Setup | undefined;

afterEach(async () => {
  await setup?.close();
  setup = undefined;
});

async function start(extra: Record<string, Spec> = {}): Promise<Setup> {
  const lib = libraryHarness();
  const bridge = new LibraryBridge(extra);
  const connection = new BridgeConnection({ open: async () => bridge.link(), owned: true, label: "fake Blender" });
  await connection.connect();
  const commands = commandsFromDescribe(bridge.describe());
  const server = createServer({ connection, workspace: lib.workspace, commands, library: lib.library });
  const client = await connectClient({ server, connection, workspace: lib.workspace, commands, mode: "headless" });
  setup = {
    client,
    bridge,
    lib,
    close: async () => {
      await client.close();
      await connection.close();
    },
  };
  return setup;
}

const TEXTURE_MAPS = { Diffuse: "diff", nor_gl: "nor_gl", Rough: "rough", AO: "ao", Displacement: "disp" };

async function downloadAll(lib: LibraryHarness, client: Client): Promise<void> {
  serveBodies(lib.polyHaven, "abandoned_parking", new Map([[HDRI_1K, Buffer.from("tiny hdr")]]));
  serveBodies(lib.polyHaven, "aerial_asphalt_01", new Map(Object.values(TEXTURE_MAPS).map((map) => [textureUrl(map, "1k"), Buffer.from(map)])));
  serveBodies(lib.polyHaven, "Barrel_01", barrelBodies());
  for (const id of ["abandoned_parking", "aerial_asphalt_01", "Barrel_01"]) {
    const result = await call(client, "library_download", { id, resolution: "1k" });
    expect(result.isError, texts(result)).toBeFalsy();
  }
}

describe("the library tools in the MCP server", () => {
  it("are listed beside the blender_ tools", async () => {
    const { client } = await start();
    const { tools } = await client.listTools();
    const names = tools.map((tool) => tool.name);
    expect(names.filter((name) => name.startsWith("library_"))).toEqual(["library_search", "library_preview", "library_download", "library_apply"]);
    expect(names).toContain("blender_set_world_hdri");
    const download = tools.find((tool) => tool.name === "library_download");
    expect(download?.inputSchema.required).toEqual(["id", "resolution"]);
    expect(download?.annotations).toMatchObject({ openWorldHint: true, readOnlyHint: false });
    expect(tools.find((tool) => tool.name === "library_apply")?.annotations).toMatchObject({ openWorldHint: false });
  });

  it("returns a preview as PNG image content, fetched at the size asked for", async () => {
    const { client, lib } = await start();
    const png = readFileSync(join(FIXTURES, "thumb-abandoned_parking-64.png"));
    lib.polyHaven.route("https://cdn.polyhaven.com/asset_img/thumbs/abandoned_parking.png", () => new Response(new Uint8Array(png), { headers: { "content-type": "image/png" } }));
    const result = await call(client, "library_preview", { id: "abandoned_parking", size: 64 });
    expect(result.isError, texts(result)).toBeFalsy();
    expect(result.content).toEqual([
      { type: "text", text: `Abandoned Parking (hdri, abandoned_parking): thumbnail 64x48 px, ${png.length} bytes.` },
      { type: "image", data: png.toString("base64"), mimeType: "image/png" },
    ]);
    expect(lib.polyHaven.requested("https://cdn.polyhaven.com/")).toEqual(["https://cdn.polyhaven.com/asset_img/thumbs/abandoned_parking.png?width=64&height=64&format=png"]);
  });

  it("caps the preview's size and refuses what is not a PNG", async () => {
    const { client, lib } = await start();
    lib.polyHaven.route("https://cdn.polyhaven.com/asset_img/thumbs/abandoned_parking.png", () => new Response(new Uint8Array(1024 * 1024 + 1)));
    expect(texts(await call(client, "library_preview", { id: "abandoned_parking" }))).toBe("refused: the thumbnail is larger than the cap of 1048576 bytes");
    lib.polyHaven.route("https://cdn.polyhaven.com/asset_img/thumbs/abandoned_parking.png", () => new Response("<html></html>"));
    expect(texts(await call(client, "library_preview", { id: "abandoned_parking" }))).toBe("invalid: the thumbnail Poly Haven sent is not a PNG image");
    expect(texts(await call(client, "library_preview", { id: "abandoned_parking", size: 2048 }))).toMatch(/^refused: bad arguments: size/);
  });

  it("sets a downloaded HDRI as the world through set_world_hdri, also offline", async () => {
    const { client, lib, bridge } = await start();
    await downloadAll(lib, client);
    lib.polyHaven.offline = true;
    const result = await call(client, "library_apply", { id: "abandoned_parking", strength: 1.5, rotation: 90 });
    expect(result.isError, texts(result)).toBeFalsy();
    const path = join(lib.workspace.root, "library", "hdri", "abandoned_parking", "abandoned_parking_1k.hdr");
    expect(bridge.sent("set_world_hdri")).toEqual([{ path, strength: 1.5, rotation: 90 }]);
    expect(JSON.parse(texts(result))).toMatchObject({ id: "abandoned_parking", type: "hdri", steps: [{ command: "blender_set_world_hdri" }], license: "CC0-1.0, by Sergej Majboroda" });
  });

  it("imports a downloaded model through the bridge's import", async () => {
    const { client, lib, bridge } = await start();
    await downloadAll(lib, client);
    expect((await call(client, "library_apply", { id: "Barrel_01" })).isError).toBeFalsy();
    expect(bridge.sent("import")).toEqual([{ path: join(lib.workspace.root, "library", "model", "Barrel_01", "Barrel_01_1k.gltf") }]);
  });

  it("explains that a texture set needs material_pbr when the bridge lacks it", async () => {
    const { client, lib, bridge } = await start();
    await downloadAll(lib, client);
    const result = await call(client, "library_apply", { id: "aerial_asphalt_01", object: "Floor" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toBe(
      "failed: building a material from a texture set needs the bridge command material_pbr, which this Blender does not offer yet; the maps are downloaded in library/texture/aerial_asphalt_01/",
    );
    expect(bridge.requests.filter((request) => request.cmd !== "describe")).toEqual([]);
  });

  it("builds a PBR material with material_pbr and gives it to the object", async () => {
    const { client, lib, bridge } = await start({ material_pbr: MATERIAL_PBR });
    await downloadAll(lib, client);
    const result = await call(client, "library_apply", { id: "aerial_asphalt_01", object: "Floor", material: "Asphalt" });
    expect(result.isError, texts(result)).toBeFalsy();
    const folder = join(lib.workspace.root, "library", "texture", "aerial_asphalt_01");
    expect(bridge.sent("material_pbr")).toEqual([
      {
        name: "Asphalt",
        base_color_path: join(folder, "aerial_asphalt_01_diff_1k.jpg"),
        normal_path: join(folder, "aerial_asphalt_01_nor_gl_1k.jpg"),
        roughness_path: join(folder, "aerial_asphalt_01_rough_1k.jpg"),
        ao_path: join(folder, "aerial_asphalt_01_ao_1k.jpg"),
        height_path: join(folder, "aerial_asphalt_01_disp_1k.jpg"),
        normal_convention: "opengl",
      },
    ]);
    expect(bridge.sent("assign_material")).toEqual([{ name: "Floor", material: "Asphalt" }]);
  });

  it("passes the DirectX convention for a DirectX normal map", async () => {
    const { client, lib, bridge } = await start({ material_pbr: MATERIAL_PBR });
    serveBodies(lib.polyHaven, "aerial_asphalt_01", new Map(["diff", "nor_dx"].map((map) => [textureUrl(map, "1k"), Buffer.from(map)])));
    expect((await call(client, "library_download", { id: "aerial_asphalt_01", resolution: "1k", maps: ["Diffuse", "nor_dx"] })).isError).toBeFalsy();
    expect((await call(client, "library_apply", { id: "aerial_asphalt_01" })).isError).toBeFalsy();
    const folder = join(lib.workspace.root, "library", "texture", "aerial_asphalt_01");
    expect(bridge.sent("material_pbr")).toEqual([
      { name: "aerial_asphalt_01", base_color_path: join(folder, "aerial_asphalt_01_diff_1k.jpg"), normal_path: join(folder, "aerial_asphalt_01_nor_dx_1k.jpg"), normal_convention: "directx" },
    ]);
    expect(bridge.sent("assign_material")).toEqual([]);
  });

  it("fails clearly when material_pbr has no input for the downloaded maps", async () => {
    const odd: Spec = { description: "Build a material.", schema: object({ name: text("Material name."), sparkle: text("Sparkle image name.") }, ["name"]) };
    const { client, lib } = await start({ material_pbr: odd });
    await downloadAll(lib, client);
    expect(texts(await call(client, "library_apply", { id: "aerial_asphalt_01" }))).toBe(
      "failed: material_pbr takes name, sparkle, and none of them fits the downloaded maps Diffuse, nor_gl, Rough, AO, Displacement",
    );
  });

  it("refuses to apply what is not downloaded, is incomplete, or with options of another type", async () => {
    const { client, lib, bridge } = await start();
    expect(texts(await call(client, "library_apply", { id: "abandoned_parking" }))).toBe(
      "not_found: abandoned_parking is not downloaded (no library/<type>/abandoned_parking/LICENSE.json); download it first with library_download",
    );
    await downloadAll(lib, client);
    expect(texts(await call(client, "library_apply", { id: "Barrel_01", strength: 2 }))).toBe("refused: strength applies only to an HDRI, and Barrel_01 is a model");
    expect(texts(await call(client, "library_apply", { id: "abandoned_parking", object: "Cube" }))).toBe("refused: object applies only to a texture, and abandoned_parking is an HDRI");
    writeFileSync(join(lib.workspace.root, "library", "hdri", "abandoned_parking", "abandoned_parking_1k.hdr"), "swapped");
    expect(texts(await call(client, "library_apply", { id: "abandoned_parking" }))).toBe(
      "invalid: library/hdri/abandoned_parking is incomplete (abandoned_parking_1k.hdr is 7 bytes, not 8); download it again",
    );
    expect(bridge.sent("set_world_hdri")).toEqual([]);
  });

  it("still lists blender_ refusals as before for an unknown tool", async () => {
    const { client } = await start();
    const result = await call(client, "library_unknown", {});
    expect(result.isError).toBe(true);
    expect(texts(result)).toContain("Unknown tool library_unknown");
  });
});
