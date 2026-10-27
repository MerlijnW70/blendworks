import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { compareAnalyses, floatTolerance, quantisationTolerance } from "../../src/package/equivalence.js";
import { buildGlb, parseGlb } from "../../src/package/glb.js";
import { compressionArguments } from "../../src/package/gltfpack.js";
import { compress } from "../../src/package/compress.js";
import type { Ktx2Info } from "../../src/package/ktx2.js";
import { gpuMemory } from "../../src/package/memory.js";
import { selectNative } from "../../src/package/native.js";
import { inspect, type Inspected } from "../../src/package/pipeline.js";
import { readImages, type ColourQuality, type ImageDetail } from "../../src/package/textures.js";
import { selectGltfpack } from "../../src/package/tool.js";
import { TEXTURED_MIP_LEVELS, TEXTURED_SIZE, texturedGlb } from "./textured.js";

const NATIVE = await selectNative();
const PRESENT = NATIVE.tool?.ktx2.ktx2 === true;
const TIMEOUT_MS = 120_000;

const folder = mkdtempSync(join(tmpdir(), "blendworks-ktx2-"));

async function inspected(name: string, bytes: Uint8Array): Promise<Inspected> {
  const path = join(folder, name);
  writeFileSync(path, bytes);
  return inspect(path, TIMEOUT_MS);
}

function compare(source: Inspected, packed: Inspected, colourQuality: ColourQuality = "compact") {
  return compareAnalyses({
    reference: source.analysis,
    candidate: packed.analysis,
    tolerance: Math.max(quantisationTolerance(source.analysis.worldBox), floatTolerance(source.analysis.worldBox)),
    referenceInfo: source.info,
    candidateInfo: packed.info,
    textures: { referenceImages: source.images, candidateImages: packed.images, plan: { ktx2: true, colourQuality } },
  });
}

function headerOf(image: ImageDetail): Ktx2Info {
  if (image.ktx2 === null) throw new Error(`image ${image.index} is not KTX2: ${image.error ?? image.mimeType}`);
  return image.ktx2;
}

function imageNamed(packed: Inspected, name: string): ImageDetail {
  const index = (packed.parts.json.images as { name: string }[]).findIndex((image) => image.name === name);
  if (index < 0) throw new Error(`no image named ${name}`);
  return packed.images[index]!;
}

describe.skipIf(!PRESENT)("real KTX2 from the native gltfpack", { timeout: TIMEOUT_MS }, () => {
  const input = texturedGlb();
  let source: Inspected;
  let packed: Inspected;
  let arguments_: string[];

  beforeAll(async () => {
    source = await inspected("source.glb", input);
    const result = await compress(input, { meshopt: true, ktx2: true, hasImages: true });
    expect(result.gltfpack.kind).toBe("native");
    expect(result.ktx2.status).toBe("written");
    arguments_ = result.arguments;
    packed = await inspected("packed.glb", result.output);
  });

  it("writes every texture as KTX2 at its original size with the full mip chain", () => {
    expect(packed.images).toHaveLength(5);
    for (const image of packed.images) {
      expect(image.mimeType, `image ${image.index}`).toBe("image/ktx2");
      expect(image.error).toBeNull();
      expect(headerOf(image)).toMatchObject({ width: TEXTURED_SIZE.width, height: TEXTURED_SIZE.height, levelCount: TEXTURED_MIP_LEVELS, faceCount: 1, layerCount: 1 });
    }
  });

  it("encodes colour maps as ETC1S in sRGB, and normal and data maps as UASTC in a linear colour space", () => {
    for (const name of ["painted_baseColor", "glass_baseColor", "glass_emissive"]) {
      expect(headerOf(imageNamed(packed, name)), name).toMatchObject({ codec: "etc1s", transfer: "srgb", supercompression: 1 });
    }
    for (const name of ["painted_normal", "painted_metallicRoughness"]) {
      expect(headerOf(imageNamed(packed, name)), name).toMatchObject({ codec: "uastc", transfer: "linear" });
    }
  });

  it("keeps the alpha channel of a colour map in a second ETC1S slice", () => {
    expect(headerOf(imageNamed(packed, "glass_baseColor")).alpha).toBe(true);
    expect(headerOf(imageNamed(packed, "painted_baseColor")).alpha).toBe(false);
  });

  it("passes the Khronos validator with no errors and declares KHR_texture_basisu as used and required", () => {
    expect(packed.validation.errors).toBe(0);
    expect(source.validation.errors).toBe(0);
    expect(packed.analysis.extensionsUsed).toContain("KHR_texture_basisu");
    expect(packed.analysis.extensionsRequired).toContain("KHR_texture_basisu");
    expect(packed.analysis.textures.map((texture) => [texture.source, texture.basisu])).toEqual([0, 1, 2, 3, 4].map((index) => [null, index]));
  });

  it("is equivalent to the uncompressed file, texture slots, counts and dimensions included", () => {
    const equivalence = compare(source, packed);
    expect(equivalence.checks.filter((check) => !check.pass)).toEqual([]);
    const texture = equivalence.checks.find((check) => check.name === "textures");
    expect(texture?.detail).toBe("5 texture slots in 5 images, KTX2 with the right codec, colour space and a full mip chain");
    expect(equivalence.pass).toBe(true);
  });

  it("takes the GPU memory from the compressed formats: far less than RGBA8 with mips", () => {
    const before = gpuMemory(source.parts, source.analysis, source.info);
    const after = gpuMemory(packed.parts, packed.analysis, packed.info);
    expect(before.images).toHaveLength(5);
    expect(before.textureBytes).toBe(5 * 4 * (96 * 64 + 48 * 32 + 24 * 16 + 12 * 8 + 6 * 4 + 3 * 2 + 1));
    const blocks = 24 * 16 + 12 * 8 + 6 * 4 + 3 * 2 + 2 * 1 + 1 + 1;
    expect(blocks).toBe(514);
    expect(after.textureBytes).toBe(blocks * (8 + 16 + 8 + 16 + 16));
    expect(after.textureBytes).toBeLessThan(before.textureBytes / 3);
    expect(after.images.map((image) => image.format).sort()).toEqual(["etc1s", "etc1s", "etc1s", "uastc", "uastc"]);
  });

  it("asks for the documented settings", () => {
    expect(arguments_.slice(0, 6)).toEqual(["-kn", "-km", "-ke", "-cc", "-tc", "-tu"]);
    expect(arguments_).toContain("normal,attrib");
  });

  it("fails the equivalence when a normal map is encoded as ETC1S, as plain -tc does for every texture", async () => {
    const tool = await selectGltfpack();
    const allEtc1s = await tool.run(input, ["-kn", "-km", "-ke", "-cc", "-tc"]);
    const wrong = await inspected("all-etc1s.glb", allEtc1s.output);
    expect(headerOf(imageNamed(wrong, "painted_normal")).codec).toBe("etc1s");
    const equivalence = compare(source, wrong);
    expect(equivalence.pass).toBe(false);
    const texture = equivalence.checks.find((check) => check.name === "textures");
    expect(texture?.pass).toBe(false);
    expect(texture?.detail).toContain("painted normal map is ETC1S, a normal map must be UASTC");
    expect(texture?.detail).toContain("painted metallicRoughness map is ETC1S, a metallicRoughness map must be UASTC");
  });

  it("accepts UASTC colour maps only under high colour quality", async () => {
    const tool = await selectGltfpack();
    const high = await tool.run(input, compressionArguments({ meshopt: true, ktx2: true, colourQuality: "high" }, { ktx2: true, reason: null }));
    const upgraded = await inspected("high.glb", high.output);
    expect(headerOf(imageNamed(upgraded, "painted_baseColor")).codec).toBe("uastc");
    expect(compare(source, upgraded, "high").pass).toBe(true);
    expect(compare(source, upgraded, "compact").pass).toBe(false);
    expect(upgraded.bytes).toBeGreaterThan(packed.bytes);
  });

  it("fails the equivalence when a KTX2 header is corrupt", async () => {
    const { json, bin } = parseGlb(new Uint8Array(readFileSync(join(folder, "packed.glb"))));
    const view = (json.bufferViews as { byteOffset?: number }[])[(json.images as { bufferView: number }[])[1]!.bufferView]!;
    const broken = bin!.slice();
    broken[view.byteOffset ?? 0] = 0;
    const corrupt = await inspected("corrupt.glb", buildGlb(json, broken));
    expect(readImages(corrupt.parts, corrupt.analysis, corrupt.info)[1]?.error).toContain("KTX2 identifier");
    const equivalence = compare(source, corrupt);
    expect(equivalence.pass).toBe(false);
    expect(equivalence.checks.find((check) => check.name === "textures")?.detail).toBe("image 1: the file does not start with the KTX2 identifier");
  });

  it("runs sandboxed and reports how", async () => {
    const tool = await selectGltfpack();
    expect(tool.info).toMatchObject({ kind: "native", ktx2: true, meshopt: true, nativeSkipped: null });
    expect(tool.info.isolation?.memory).toMatch(/4096 MB/);
    expect(tool.info.version).toBe("1.3");
  });
});
