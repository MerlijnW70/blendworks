import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startSession, type Session } from "../src/session.js";
import { validateGltf, VALIDATOR_DEFAULTS } from "../src/judge/validator.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const LIMITS = { maxBytes: VALIDATOR_DEFAULTS.maxBytes, heapMb: VALIDATOR_DEFAULTS.heapMb, timeoutMs: 60_000 };

interface Primitive {
  attributes: Record<string, number>;
}
interface Glb {
  meshes: { primitives: Primitive[] }[];
  nodes: { name?: string }[];
  images?: { mimeType: string }[];
  accessors: { count: number; min?: number[]; max?: number[] }[];
  extensionsUsed?: string[];
}

function glb(path: string): Glb {
  const data = readFileSync(path);
  expect(data.subarray(0, 4).toString("ascii")).toBe("glTF");
  return JSON.parse(data.subarray(20, 20 + data.readUInt32LE(12)).toString("utf8")) as Glb;
}

function attributes(document: Glb): string[] {
  return Object.keys(document.meshes[0]?.primitives[0]?.attributes ?? {}).sort();
}

describe("export options", workBudget(600_000), () => {
  const workspace = mkdtempSync(join(tmpdir(), "blendworks-export-"));
  let session: Session;
  const path = (name: string) => join(workspace, name);

  async function exported(name: string, options: Record<string, unknown> = {}): Promise<Glb> {
    const result = await session.call("export", { path: name, names: ["Crate"], ...options });
    expect(result["bytes"]).toBeGreaterThan(0);
    return glb(path(name));
  }

  beforeAll(withWorkBudget(300_000, async () => {
    session = await startSession({ workspace });
    await session.call("add_primitive", { type: "cube", name: "Crate", size: 1 });
    await session.call("transform", { name: "Crate", scale: [1, 1, 2] });
    await session.call("apply_transform", { name: "Crate", scale: true });
    await session.call("uv_smart_project", { name: "Crate", island_margin: 0.02 });
    await session.call("material_procedural", { name: "Planks", wood: { seed: 3, bump: 1.0 } });
    await session.call("assign_material", { name: "Crate", material: "Planks" });
    await session.call("bake", { names: ["Crate"], channels: ["base_color", "roughness", "metallic", "normal"], size: 64, rewire: true, device: "auto" });
  }));

  afterAll(async () => {
    await session?.close();
    rmSync(workspace, { recursive: true, force: true });
  });

  it("passes the glTF validator with 0 errors and 0 warnings on default options", async () => {
    const document = await exported("default.glb");
    const validation = await validateGltf(path("default.glb"), "glb", LIMITS);
    expect([validation.errors, validation.warnings], JSON.stringify(validation.issues)).toEqual([0, 0]);
    expect(attributes(document)).toContain("TANGENT");
    expect(document.images?.map((image) => image.mimeType)).toEqual(["image/png", "image/png", "image/png"]);
    expect(document.extensionsUsed ?? []).not.toContain("KHR_draco_mesh_compression");
  });

  it("writes tangents by default for a normal-mapped mesh, and only when asked for a plain one", async () => {
    expect(attributes(await exported("no-tangents.glb", { tangents: false }))).not.toContain("TANGENT");
    expect(attributes(await exported("tangents.glb", { tangents: true }))).toContain("TANGENT");
    await session.call("add_primitive", { type: "cube", name: "Plain", size: 1 });
    await session.call("export", { path: "plain.glb", names: ["Plain"] });
    expect(attributes(glb(path("plain.glb")))).not.toContain("TANGENT");
    await session.call("export", { path: "plain-tangents.glb", names: ["Plain"], tangents: true });
    await session.call("delete", { names: ["Plain"] });
  });

  it("triangulates n-gons for the export so tangents survive, and leaves the scene alone", async () => {
    await session.call("add_primitive", { type: "cylinder", name: "Drum", radius: 0.5, depth: 1, segments: 24 });
    await session.call("uv_smart_project", { name: "Drum" });
    await session.call("assign_material", { name: "Drum", material: "Crate_baked" });
    await session.call("export", { path: "drum.glb", names: ["Drum"] });
    const document = glb(path("drum.glb"));
    expect(attributes(document)).toContain("TANGENT");
    const validation = await validateGltf(path("drum.glb"), "glb", LIMITS);
    expect([validation.errors, validation.warnings], JSON.stringify(validation.issues)).toEqual([0, 0]);
    const info = (await session.call("scene_info", { names: "Drum" })) as { objects: { modifiers: unknown[]; mesh: { faces: number } }[] };
    expect(info.objects[0]?.modifiers).toEqual([]);
    expect(info.objects[0]?.mesh.faces).toBe(26);
    expect(await session.send("export", { path: "drum-live.glb", names: ["Drum"], tangents: true, apply_modifiers: false })).toMatchObject({ ok: false, error: { code: "bad_args" } });
    await session.call("export", { path: "drum-live.glb", names: ["Drum"], apply_modifiers: false });
    expect(attributes(glb(path("drum-live.glb")))).not.toContain("TANGENT");
    await session.call("delete", { names: ["Drum"] });
  });

  it("converts textures to JPEG with a quality, or to PNG", async () => {
    const jpeg = await exported("jpeg.glb", { image_format: "jpeg", jpeg_quality: 40 });
    expect(jpeg.images?.map((image) => image.mimeType)).toEqual(["image/jpeg", "image/jpeg", "image/jpeg"]);
    const high = await exported("jpeg-high.glb", { image_format: "jpeg", jpeg_quality: 95 });
    expect(high.images?.length).toBe(3);
    expect(readFileSync(path("jpeg-high.glb")).length).toBeGreaterThan(readFileSync(path("jpeg.glb")).length);
    const png = await exported("png.glb", { image_format: "png" });
    expect(png.images?.map((image) => image.mimeType)).toEqual(["image/png", "image/png", "image/png"]);
    expect((await validateGltf(path("jpeg.glb"), "glb", LIMITS)).errors).toBe(0);
  });

  it("keeps JPEG sources under auto and converts them under png", async () => {
    await session.call("image_save", { name: "Crate_base_color", path: "maps/base.jpg", quality: 90 });
    await session.call("material_pbr", { name: "FromJpeg", base_color_path: "maps/base.jpg" });
    await session.call("add_primitive", { type: "cube", name: "Jpeg", size: 1 });
    await session.call("uv_smart_project", { name: "Jpeg" });
    await session.call("assign_material", { name: "Jpeg", material: "FromJpeg" });
    await session.call("export", { path: "jpeg-source.glb", names: ["Jpeg"] });
    expect(glb(path("jpeg-source.glb")).images?.map((image) => image.mimeType)).toEqual(["image/jpeg"]);
    await session.call("export", { path: "jpeg-source-png.glb", names: ["Jpeg"], image_format: "png" });
    expect(glb(path("jpeg-source-png.glb")).images?.map((image) => image.mimeType)).toEqual(["image/png"]);
    await session.call("delete", { names: ["Jpeg"] });
  });

  it("compresses with Draco and the file still validates", async () => {
    const plain = readFileSync(path("default.glb")).length;
    const document = await exported("draco.glb", { draco: true, draco_level: 10 });
    expect(document.extensionsUsed).toContain("KHR_draco_mesh_compression");
    const validation = await validateGltf(path("draco.glb"), "glb", LIMITS);
    expect([validation.errors, validation.warnings], JSON.stringify(validation.issues)).toEqual([0, 0]);
    expect(readFileSync(path("draco.glb")).length).not.toBe(plain);
  });

  it("applies modifiers unless told not to", async () => {
    await session.call("add_primitive", { type: "cube", name: "Row", size: 1 });
    await session.call("array", { name: "Row", count: 4, relative_offset: [1.5, 0, 0], apply: false });
    await session.call("export", { path: "applied.glb", names: ["Row"] });
    await session.call("export", { path: "live.glb", names: ["Row"], apply_modifiers: false });
    const count = (document: Glb) => document.accessors[document.meshes[0]?.primitives[0]?.attributes["POSITION"] ?? 0]?.count;
    expect(count(glb(path("applied.glb")))).toBe(4 * 24);
    expect(count(glb(path("live.glb")))).toBe(24);
    await session.call("delete", { names: ["Row"] });
  });

  it("leaves hidden objects out unless include_hidden is set", async () => {
    await session.call("add_primitive", { type: "cube", name: "Cutter", size: 0.2, location: [0, 0, 5] });
    await session.call("add_primitive", { type: "cube", name: "Target", size: 1, location: [4, 0, 0] });
    await session.call("boolean", { name: "Target", cutter: "Cutter", operation: "difference", cutter_action: "hide" });
    const names = (document: Glb) => document.nodes.map((node) => node.name).sort();
    await session.call("export", { path: "visible.glb" });
    expect(names(glb(path("visible.glb")))).toEqual(["Crate", "Target"]);
    await session.call("export", { path: "with-hidden.glb", include_hidden: true });
    expect(names(glb(path("with-hidden.glb")))).toEqual(["Crate", "Cutter", "Target"]);
    const refused = await session.send("export", { path: "cutter.glb", names: ["Cutter"] });
    expect(refused).toMatchObject({ ok: false, error: { code: "bad_args" } });
    await session.call("export", { path: "cutter.glb", names: ["Cutter"], include_hidden: true });
    expect(names(glb(path("cutter.glb")))).toEqual(["Cutter"]);
    const after = (await session.call("scene_info", { names: "Cutter" })) as { objects: { visible: boolean }[] };
    expect(after.objects[0]?.visible).toBe(false);
    await session.call("delete", { names: ["Cutter", "Target"] });
  });

  it("writes Y up by default and keeps Blender's Z up with yup false", async () => {
    const extent = (document: Glb, axis: number) => {
      const accessor = document.accessors[document.meshes[0]?.primitives[0]?.attributes["POSITION"] ?? 0];
      return (accessor?.max?.[axis] ?? 0) - (accessor?.min?.[axis] ?? 0);
    };
    const up = await exported("y-up.glb");
    const flat = await exported("z-up.glb", { yup: false });
    expect([extent(up, 1), extent(up, 2)]).toEqual([expect.closeTo(2, 4), expect.closeTo(1, 4)]);
    expect([extent(flat, 1), extent(flat, 2)]).toEqual([expect.closeTo(1, 4), expect.closeTo(2, 4)]);
  });

  it("refuses options that do not apply", async () => {
    for (const args of [
      { path: "a.fbx", tangents: true },
      { path: "a.obj", draco: false },
      { path: "a.glb", jpeg_quality: 50 },
      { path: "a.glb", draco_level: 3 },
      { path: "a.glb", image_format: "bmp" },
    ]) {
      expect(await session.send("export", { names: ["Crate"], include_hidden: true, ...args }), JSON.stringify(args)).toMatchObject({ ok: false, error: { code: "bad_args" } });
    }
  });
});
