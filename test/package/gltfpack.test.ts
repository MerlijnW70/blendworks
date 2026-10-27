import { describe, expect, it } from "vitest";
import { analyse } from "../../src/package/analysis.js";
import { compress } from "../../src/package/compress.js";
import { buildGlb, parseGlb } from "../../src/package/glb.js";
import { compressionArguments, GltfpackError, probeTextureSupport, runGltfpack } from "../../src/package/gltfpack.js";
import { gpuMemory, imageBytes, mipChain } from "../../src/package/memory.js";
import { tinyTexturedGlb } from "../../src/package/tiny.js";

function imageBytesOf(glb: Uint8Array): Uint8Array {
  const { json, bin } = parseGlb(glb);
  const view = (json.bufferViews as { byteOffset?: number; byteLength: number }[])[(json.images as { bufferView: number }[])[0]!.bufferView]!;
  return bin!.slice(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
}

describe("the gltfpack build", () => {
  it("cannot write KTX2 textures, and says why", async () => {
    const support = await probeTextureSupport();
    expect(support.ktx2).toBe(false);
    expect(support.reason).toContain("without BasisU support");
  });

  it("refuses texture compression and texture processing instead of faking them", async () => {
    await expect(runGltfpack(tinyTexturedGlb(), ["-tc"])).rejects.toBeInstanceOf(GltfpackError);
    await expect(runGltfpack(tinyTexturedGlb(), ["-tl", "64"])).rejects.toThrow("only supported when texture compression is enabled");
  });

  it("meshopt-compresses a file that parses and validates as a glTF binary", async () => {
    const packed = await runGltfpack(tinyTexturedGlb(), ["-kn", "-km", "-ke", "-cc"]);
    const { json } = parseGlb(packed.output);
    expect(json.extensionsUsed).toContain("EXT_meshopt_compression");
    expect(json.extensionsUsed).toContain("KHR_mesh_quantization");
    expect(analyse(json).triangles).toBe(1);
    const plain = await runGltfpack(tinyTexturedGlb(), ["-kn", "-km", "-ke"]);
    expect(parseGlb(plain.output).json.extensionsUsed).not.toContain("EXT_meshopt_compression");
  });

  it("keeps the named nodes the way the package check expects", async () => {
    const packed = await runGltfpack(tinyTexturedGlb(), ["-kn", "-km", "-cc"]);
    expect(analyse(parseGlb(packed.output).json).paths).toEqual(["/tiny"]);
  });
});

describe("compression options", () => {
  const unavailable = { ktx2: false, reason: "no encoder" };
  const available = { ktx2: true, reason: null };

  it("asks for meshopt with -cc and always keeps names, materials and extras", () => {
    expect(compressionArguments({ meshopt: true, ktx2: false }, unavailable)).toEqual(["-kn", "-km", "-ke", "-cc"]);
    expect(compressionArguments({ meshopt: false, ktx2: false }, unavailable)).toEqual(["-kn", "-km", "-ke"]);
  });

  it("asks for KTX2 only when the build can write it, with UASTC for normal and data maps and ETC1S for colour", () => {
    expect(compressionArguments({ meshopt: true, ktx2: true }, unavailable)).toEqual(["-kn", "-km", "-ke", "-cc"]);
    expect(compressionArguments({ meshopt: true, ktx2: true }, available)).toEqual(["-kn", "-km", "-ke", "-cc", "-tc", "-tu", "normal,attrib"]);
    expect(compressionArguments({ meshopt: false, ktx2: true, colourQuality: "high" }, available)).toEqual(["-kn", "-km", "-ke", "-tc", "-tu", "color,normal,attrib"]);
  });

  it("reports KTX2 as unavailable and copies the textures unchanged", async () => {
    const input = tinyTexturedGlb();
    const result = await compress(input, { meshopt: true, ktx2: true, hasImages: true });
    expect(result.ktx2.status).toBe("unavailable");
    expect(result.ktx2.reason).toContain("without BasisU support");
    expect(result.ktx2.reason).toContain("the textures are copied unchanged");
    expect(imageBytesOf(result.output)).toEqual(imageBytesOf(input));
    expect((await compress(input, { meshopt: true, ktx2: false, hasImages: true })).ktx2.status).toBe("not requested");
  });
});

describe("GPU memory", () => {
  it("sums the mip chain of an RGBA8 image as the design states", () => {
    expect(mipChain(48, 20).map(([w, h]) => w * h)).toEqual([960, 240, 60, 12, 3, 1]);
    expect(imageBytes(4096, 4096, "rgba8")).toBe(89_478_484);
    expect(imageBytes(48, 20, "rgba8")).toBe(5104);
  });

  it("counts block-compressed images by 4 by 4 blocks of 16 bytes (UASTC) or 8 bytes (ETC1S)", () => {
    expect(imageBytes(256, 256, "uastc")).toBe(5463 * 16);
    expect(imageBytes(256, 256, "etc1s")).toBe(5463 * 8);
  });

  it("estimates textures from the validator's image sizes, KTX2 by its supercompression scheme, and meshes from the accessors", () => {
    const header = new Uint8Array(64);
    new DataView(header.buffer).setUint32(44, 1, true);
    const document = {
      asset: { version: "2.0" },
      nodes: [{ name: "a", mesh: 0 }],
      scenes: [{ nodes: [0] }],
      meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1 }] }],
      accessors: [
        { componentType: 5126, count: 4, type: "VEC3", min: [0, 0, 0], max: [1, 1, 1] },
        { componentType: 5123, count: 6, type: "SCALAR" },
      ],
      images: [
        { mimeType: "image/png", bufferView: 0 },
        { mimeType: "image/ktx2", bufferView: 1 },
      ],
      bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 8 }, { buffer: 0, byteOffset: 0, byteLength: 64 }],
    };
    const parts = parseGlb(buildGlb(document, header));
    const info = {
      resources: [
        { pointer: "/images/0", image: { width: 16, height: 16 } },
        { pointer: "/images/1", image: { width: 16, height: 16 } },
      ],
    };
    const memory = gpuMemory(parts, analyse(document), info);
    expect(memory.meshBytes).toBe(4 * 12 + 6 * 2);
    expect(memory.images.map((image) => [image.format, image.bytes])).toEqual([
      ["rgba8", 4 * (256 + 64 + 16 + 4 + 1)],
      ["etc1s", (16 + 4 + 1 + 1 + 1) * 8],
    ]);
    expect(memory.totalBytes).toBe(memory.textureBytes + memory.meshBytes);
  });
});
