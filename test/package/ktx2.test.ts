import { describe, expect, it } from "vitest";
import { Ktx2Error, fullMipCount, parseKtx2 } from "../../src/package/ktx2.js";
import { ktx2File, withField } from "./ktx2-fixture.js";

describe("the KTX2 header", () => {
  it("counts a full mip chain from the longer side", () => {
    expect([1, 2, 3, 4, 96, 2048].map((side) => fullMipCount(side, 1))).toEqual([1, 2, 2, 3, 7, 12]);
    expect(fullMipCount(96, 64)).toBe(7);
    expect(fullMipCount(2048, 2048)).toBe(12);
  });

  it("reads the size, the mip levels, the codec, the colour space and the alpha slice of an ETC1S colour map", () => {
    const info = parseKtx2(ktx2File({ width: 96, height: 64, codec: "etc1s", transfer: "srgb", alpha: true }));
    expect(info).toMatchObject({ width: 96, height: 64, levelCount: 7, codec: "etc1s", transfer: "srgb", alpha: true, supercompression: 1, faceCount: 1, layerCount: 1 });
    expect(info.levels).toHaveLength(7);
    expect(info.levels[2]).toMatchObject({ bytes: 64, uncompressedBytes: 128 });
  });

  it("reads a UASTC data map as linear without an alpha slice", () => {
    const info = parseKtx2(ktx2File({ width: 8, height: 8, codec: "uastc", transfer: "linear" }));
    expect(info).toMatchObject({ levelCount: 4, codec: "uastc", transfer: "linear", alpha: false, supercompression: 2 });
  });

  it("reads other codecs and colour spaces as other, so no check can mistake them", () => {
    expect(parseKtx2(ktx2File({ width: 4, height: 4, codec: "other", levels: 3 }))).toMatchObject({ codec: "other" });
  });

  it("counts a file that asks for its mips at load time as one level", () => {
    expect(parseKtx2(ktx2File({ width: 64, height: 64, levels: 0 })).levelCount).toBe(1);
  });

  const good = ktx2File({ width: 16, height: 16, codec: "etc1s", transfer: "srgb" });
  const broken: [string, Uint8Array, string][] = [
    ["an empty file", new Uint8Array(0), "shorter than the 80-byte"],
    ["a truncated header", good.subarray(0, 60), "shorter than the 80-byte"],
    ["a wrong identifier", withField(good, 0, 0), "KTX2 identifier"],
    ["a zero width", withField(good, 20, 0), "is empty"],
    ["a zero height", withField(good, 24, 0), "is empty"],
    ["a depth", withField(good, 28, 4), "glTF textures are 2D"],
    ["six faces", withField(good, 36, 6), "6 faces"],
    ["an array", withField(good, 32, 3), "3 layers"],
    ["more mip levels than the size allows", withField(good, 40, 6), "cannot fit a 16 by 16 image"],
    ["an unknown supercompression scheme", withField(good, 44, 9), "scheme 9 is unknown"],
    ["ETC1S without BasisLZ", withField(good, 44, 0), "must use BasisLZ"],
    ["a level index cut off by the end of the file", good.subarray(0, 100), "level index"],
    ["a level that lies outside the file", good.subarray(0, good.byteLength - 8), "mip level 4 lies outside"],
    ["a descriptor outside the file", withField(good, 48, 100000), "data format descriptor lies outside"],
    ["a descriptor too short for a basic block", withField(good, 52, 12), "too short for a basic block"],
    ["a descriptor whose size disagrees with the header", withField(good, 52, 40), "declares a size"],
  ];
  it.each(broken)("refuses %s", (_, bytes, message) => {
    expect(() => parseKtx2(bytes)).toThrow(Ktx2Error);
    expect(() => parseKtx2(bytes)).toThrow(message);
  });

  it("refuses a descriptor of the wrong version and a block that does not fit", () => {
    const base = 80 + 5 * 24;
    const versioned = withField(good, base + 8, 1 | (40 << 16));
    expect(() => parseKtx2(versioned)).toThrow("version 1");
    const oversized = withField(good, base + 8, 2 | (200 << 16));
    expect(() => parseKtx2(oversized)).toThrow("does not fit");
    const vendor = withField(good, base + 4, 7);
    expect(() => parseKtx2(vendor)).toThrow("not a basic block");
  });

  it("refuses a level whose offset points into the header or index", () => {
    const copy = good.slice();
    new DataView(copy.buffer).setBigUint64(80, 10n, true);
    expect(() => parseKtx2(copy)).toThrow("mip level 0 lies outside");
  });
});
