import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { analyse } from "../../src/package/analysis.js";
import { compress } from "../../src/package/compress.js";
import { parseGlb } from "../../src/package/glb.js";
import { compressionArguments, GltfpackError, probeTextureSupport, runGltfpack } from "../../src/package/gltfpack.js";
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
    const qualities = ["-tq", "color", "8", "-tq", "normal", "8", "-tq", "attrib", "8"];
    expect(compressionArguments({ meshopt: true, ktx2: true }, available)).toEqual(["-kn", "-km", "-ke", "-cc", "-tc", "-tu", "normal,attrib", ...qualities]);
    expect(compressionArguments({ meshopt: false, ktx2: true, colourQuality: "high", threads: 4 }, available)).toEqual(["-kn", "-km", "-ke", "-tc", "-tu", "color,normal,attrib", ...qualities, "-tj", "4"]);
  });

  it("reports KTX2 as unavailable and copies the textures unchanged", async () => {
    const input = tinyTexturedGlb();
    const select = { env: { BLENDWORKS_CACHE: mkdtempSync(join(tmpdir(), "blendworks-no-native-")) } };
    const result = await compress(input, { meshopt: true, ktx2: true, hasImages: true, select });
    expect(result.ktx2.status).toBe("unavailable");
    expect(result.ktx2.reason).toContain("without BasisU support");
    expect(result.ktx2.reason).toContain("the textures are copied unchanged");
    expect(imageBytesOf(result.output)).toEqual(imageBytesOf(input));
    expect((await compress(input, { meshopt: true, ktx2: false, hasImages: true, select })).ktx2.status).toBe("not requested");
  });
});
