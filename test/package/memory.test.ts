import { describe, expect, it } from "vitest";
import { blockBytes, gpuMemory, imageBytes, mipChain } from "../../src/package/memory.js";
import { scene } from "./image-scene.js";

describe("GPU memory of uncompressed images", () => {
  it("sums the mip chain of an RGBA8 image as the design states", () => {
    expect(mipChain(48, 20).map(([w, h]) => w * h)).toEqual([960, 240, 60, 12, 3, 1]);
    expect(imageBytes(4096, 4096, "rgba8")).toBe(89_478_484);
    expect(imageBytes(48, 20, "rgba8")).toBe(5104);
  });
});

describe("GPU memory of KTX2 images", () => {
  it("counts 16-byte blocks for UASTC, 8-byte blocks for ETC1S, and 16 bytes for ETC1S with an alpha slice", () => {
    expect(blockBytes("uastc", false)).toBe(16);
    expect(blockBytes("etc1s", false)).toBe(8);
    expect(blockBytes("etc1s", true)).toBe(16);
    expect(imageBytes(256, 256, "uastc")).toBe(5463 * 16);
    expect(imageBytes(256, 256, "etc1s")).toBe(5463 * 8);
    expect(imageBytes(256, 256, "etc1s", { alpha: true })).toBe(5463 * 16);
  });

  it("rounds every level up to whole 4 by 4 blocks and counts only the levels the file holds", () => {
    expect(imageBytes(96, 64, "uastc")).toBe((24 * 16 + 12 * 8 + 6 * 4 + 3 * 2 + 2 * 1 + 1 + 1) * 16);
    expect(imageBytes(96, 64, "uastc", { levels: 1 })).toBe(24 * 16 * 16);
    expect(imageBytes(96, 64, "uastc", { levels: 3 })).toBe((24 * 16 + 12 * 8 + 6 * 4) * 16);
    expect(imageBytes(5, 3, "etc1s", { levels: 1 })).toBe(2 * 1 * 8);
  });

  it("estimates textures from the KTX2 headers and the validator's PNG sizes, and meshes from the accessors", () => {
    const built = scene({
      images: [
        { png: { width: 16, height: 16 } },
        { ktx2: { width: 96, height: 64, codec: "etc1s", transfer: "srgb" } },
        { ktx2: { width: 96, height: 64, codec: "etc1s", transfer: "srgb", alpha: true } },
        { ktx2: { width: 96, height: 64, codec: "uastc", levels: 3 } },
        { ktx2: { width: 8, height: 8, codec: "other", levels: 2, payloadBytes: 100 } },
      ],
    });
    const document = { ...built.parts.json, meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1 }] }], nodes: [{ name: "a", mesh: 0 }], scenes: [{ nodes: [0] }], scene: 0, accessors: [{ componentType: 5126, count: 4, type: "VEC3", min: [0, 0, 0], max: [1, 1, 1] }, { componentType: 5123, count: 6, type: "SCALAR" }] };
    const memory = gpuMemory({ ...built.parts, json: document }, { ...built.analysis, accessorBytes: 4 * 12 + 6 * 2 }, built.info);
    expect(memory.meshBytes).toBe(4 * 12 + 6 * 2);
    expect(memory.images.map((image) => [image.format, image.levels, image.alpha, image.bytes])).toEqual([
      ["rgba8", 5, true, 4 * (256 + 64 + 16 + 4 + 1)],
      ["etc1s", 7, false, imageBytes(96, 64, "uastc") / 2],
      ["etc1s", 7, true, imageBytes(96, 64, "uastc")],
      ["uastc", 3, false, (24 * 16 + 12 * 8 + 6 * 4) * 16],
      ["other", 2, false, 200],
    ]);
    expect(memory.textureBytes).toBe(memory.images.reduce((sum, image) => sum + image.bytes, 0));
    expect(memory.totalBytes).toBe(memory.textureBytes + memory.meshBytes);
  });

  it("leaves out an image whose header is corrupt instead of guessing its size", () => {
    const built = scene({ images: [{ raw: new Uint8Array(100) }, { ktx2: { width: 16, height: 16, codec: "uastc" } }] });
    const memory = gpuMemory(built.parts, built.analysis, built.info);
    expect(memory.images.map((image) => image.image)).toEqual([1]);
  });
});
