import { describe, expect, it } from "vitest";
import { compareAnalyses } from "../../src/package/equivalence.js";
import { textureCheck } from "../../src/package/texture-check.js";
import { expectedCodec, expectedTransfer, type TexturePlan } from "../../src/package/textures.js";
import type { Ktx2Fixture } from "./ktx2-fixture.js";
import { scene, type SceneImage, type SceneOptions } from "./image-scene.js";

const SOURCE: SceneOptions = {
  images: [{ png: { width: 96, height: 64 } }, { png: { width: 96, height: 64 } }, { png: { width: 96, height: 64 } }],
  slots: { baseColor: 0, normal: 1, metallicRoughness: 2 },
};
const COMPACT: TexturePlan = { ktx2: true, colourQuality: "compact" };
const HIGH: TexturePlan = { ktx2: true, colourQuality: "high" };

function ktx2(overrides: Ktx2Fixture): SceneImage {
  return { ktx2: overrides };
}

const COLOUR: Ktx2Fixture = { width: 96, height: 64, codec: "etc1s", transfer: "srgb" };
const NORMAL: Ktx2Fixture = { width: 96, height: 64, codec: "uastc", transfer: "linear" };
const DATA: Ktx2Fixture = { width: 96, height: 64, codec: "uastc", transfer: "linear" };

function candidate(images: [Ktx2Fixture, Ktx2Fixture, Ktx2Fixture], extra: Partial<SceneOptions> = {}) {
  return scene({ ...SOURCE, images: images.map(ktx2), ...extra });
}

function check(candidateScene = candidate([COLOUR, NORMAL, DATA]), plan: TexturePlan = COMPACT, source = scene(SOURCE)) {
  return textureCheck({ reference: source.analysis, candidate: candidateScene.analysis, referenceImages: source.images, candidateImages: candidateScene.images, plan });
}

describe("the texture check of a compressed package", () => {
  it("accepts ETC1S colour, UASTC normal and data maps, in the right colour space, at the same size with a full mip chain", () => {
    const result = check();
    expect(result).toMatchObject({ name: "textures", pass: true });
    expect(result.detail).toBe("3 texture slots in 3 images, KTX2 with the right codec, colour space and a full mip chain");
  });

  it("fails a normal map that was encoded as ETC1S", () => {
    const result = check(candidate([COLOUR, { ...NORMAL, codec: "etc1s" }, DATA]));
    expect(result.pass).toBe(false);
    expect(result.detail).toBe("m normal map is ETC1S, a normal map must be UASTC");
  });

  it("fails a metallic-roughness map that was encoded as ETC1S", () => {
    expect(check(candidate([COLOUR, NORMAL, { ...DATA, codec: "etc1s" }])).detail).toBe("m metallicRoughness map is ETC1S, a metallicRoughness map must be UASTC");
  });

  it("fails a colour map that is UASTC unless high colour quality asked for it", () => {
    const uastcColour = candidate([{ ...COLOUR, codec: "uastc" }, NORMAL, DATA]);
    expect(check(uastcColour).detail).toBe("m baseColor map is UASTC, a baseColor map must be ETC1S");
    expect(check(uastcColour, HIGH).pass).toBe(true);
    expect(check(candidate([COLOUR, NORMAL, DATA]), HIGH).detail).toBe("m baseColor map is ETC1S, a baseColor map must be UASTC");
    expect(expectedCodec("baseColor", "high")).toBe("uastc");
    expect(expectedCodec("emissive", "compact")).toBe("etc1s");
    expect(expectedCodec("occlusion", "compact")).toBe("uastc");
  });

  it("fails colour maps in a linear colour space and data maps in sRGB", () => {
    expect(check(candidate([{ ...COLOUR, transfer: "linear" }, NORMAL, DATA])).detail).toBe("m baseColor map is linear, a baseColor map must be srgb");
    expect(check(candidate([COLOUR, { ...NORMAL, transfer: "srgb" }, DATA])).detail).toBe("m normal map is srgb, a normal map must be linear");
    expect(expectedTransfer("emissive")).toBe("srgb");
    expect(expectedTransfer("normal")).toBe("linear");
  });

  it("fails a texture without its full mip chain, from the header", () => {
    expect(check(candidate([COLOUR, { ...NORMAL, levels: 1 }, DATA])).detail).toBe("m normal map has 1 mip levels, a 96 by 64 image needs 7");
    expect(check(candidate([COLOUR, { ...NORMAL, levels: 6 }, DATA])).pass).toBe(false);
  });

  it("fails a texture whose size changed", () => {
    const result = check(candidate([COLOUR, { ...NORMAL, width: 48, height: 32 }, DATA]));
    expect(result.pass).toBe(false);
    expect(result.detail).toBe("m normal map is 48 by 32, was 96 by 64");
  });

  it("fails a file whose KTX2 header is corrupt, even when nothing else is wrong", () => {
    const corrupt = scene({ ...SOURCE, images: [ktx2(COLOUR), { raw: new Uint8Array(200).fill(3) }, ktx2(DATA)] });
    const result = check(corrupt);
    expect(result.pass).toBe(false);
    expect(result.detail).toBe("image 1: the file does not start with the KTX2 identifier");
  });

  it("fails when the extension is not declared as used and as required, or a texture bypasses it", () => {
    expect(check(candidate([COLOUR, NORMAL, DATA], { declare: "used" })).detail).toBe("KHR_texture_basisu is not in extensionsRequired");
    expect(check(candidate([COLOUR, NORMAL, DATA], { declare: "none" })).detail).toBe("KHR_texture_basisu is not in extensionsUsed; KHR_texture_basisu is not in extensionsRequired");
    const bypassed = check(candidate([COLOUR, NORMAL, DATA], { plainSource: true }));
    expect(bypassed.pass).toBe(false);
    expect(bypassed.detail).toContain("image 0 is KTX2 but no texture names it in KHR_texture_basisu");
    expect(bypassed.detail).toContain("image 0 is KTX2 but a texture uses it as a plain source");
  });

  it("fails when images were left uncompressed although KTX2 was written, or when the texture count changed", () => {
    const mixed = scene({ ...SOURCE, images: [ktx2(COLOUR), { png: { width: 96, height: 64 } }, ktx2(DATA)] });
    expect(check(mixed).detail).toBe("m normal map is not KTX2");
    const fewer = scene({ ...SOURCE, images: [ktx2(COLOUR), ktx2(NORMAL), ktx2(DATA)], slots: { baseColor: 0, normal: 1, metallicRoughness: 2 } });
    fewer.analysis.textures.pop();
    expect(check(fewer).detail).toContain("3 textures against 2");
  });

  it("compares sizes only, when KTX2 was not asked for", () => {
    const same = scene(SOURCE);
    expect(check(same, { ktx2: false, colourQuality: "compact" }).pass).toBe(true);
    const resized = scene({ ...SOURCE, images: [{ png: { width: 96, height: 64 } }, { png: { width: 48, height: 32 } }, { png: { width: 96, height: 64 } }] });
    expect(check(resized, { ktx2: false, colourQuality: "compact" }).detail).toBe("m normal map is 48 by 32, was 96 by 64");
  });

  it("fails a source image of unknown size instead of passing it unchecked", () => {
    const unknown = scene({ ...SOURCE, images: [{ png: { width: 96, height: 64 } }, { raw: new Uint8Array(8) }, { png: { width: 96, height: 64 } }] });
    unknown.images[1]!.width = null;
    const result = check(candidate([COLOUR, NORMAL, DATA]), COMPACT, unknown);
    expect(result.detail).toBe("m normal map has a source image of unknown size");
  });
});

describe("the textures check inside the equivalence", () => {
  const source = scene(SOURCE);

  function compare(candidateScene: ReturnType<typeof candidate>, plan: TexturePlan) {
    return compareAnalyses({
      reference: source.analysis,
      candidate: candidateScene.analysis,
      tolerance: 1,
      referenceInfo: { totalTriangleCount: 0 },
      candidateInfo: { totalTriangleCount: 0 },
      textures: { referenceImages: source.images, candidateImages: candidateScene.images, plan },
    });
  }

  it("is part of the verdict, so one wrongly encoded normal map makes the package not equivalent", () => {
    const good = compare(candidate([COLOUR, NORMAL, DATA]), COMPACT);
    expect(good.checks.map((entry) => entry.name)).toEqual(["hierarchy", "triangles", "bounds", "materials", "validatorCounts", "textures"]);
    expect(good.pass).toBe(true);
    const bad = compare(candidate([COLOUR, { ...NORMAL, codec: "etc1s" }, DATA]), COMPACT);
    expect(bad.pass).toBe(false);
    expect(bad.checks.find((entry) => entry.name === "textures")?.pass).toBe(false);
  });

  it("is left out when no image evidence is given", () => {
    const result = compareAnalyses({ reference: source.analysis, candidate: source.analysis, tolerance: 1, referenceInfo: { totalTriangleCount: 0 }, candidateInfo: { totalTriangleCount: 0 } });
    expect(result.checks.map((entry) => entry.name)).not.toContain("textures");
  });
});
