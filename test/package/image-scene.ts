import { analyse, type Analysis } from "../../src/package/analysis.js";
import { buildGlb, parseGlb, type GlbParts } from "../../src/package/glb.js";
import { readImages, type ImageDetail } from "../../src/package/textures.js";
import type { ValidationInfo } from "../../src/judge/validator.js";
import { ktx2File, type Ktx2Fixture } from "./ktx2-fixture.js";

export type SceneImage = { png: { width: number; height: number } } | { ktx2: Ktx2Fixture } | { raw: Uint8Array };

export type SceneOptions = {
  images: SceneImage[];
  slots?: Partial<Record<"baseColor" | "normal" | "metallicRoughness" | "emissive" | "occlusion", number>>;
  declare?: "both" | "used" | "none";
  plainSource?: boolean;
};

export type Scene = { parts: GlbParts; analysis: Analysis; info: ValidationInfo; images: ImageDetail[] };

const REFERENCES: Record<string, (index: number) => Record<string, any>> = {
  baseColor: (index: number) => ({ pbrMetallicRoughness: { baseColorTexture: { index } } }),
  metallicRoughness: (index: number) => ({ pbrMetallicRoughness: { metallicRoughnessTexture: { index } } }),
  normal: (index: number) => ({ normalTexture: { index } }),
  occlusion: (index: number) => ({ occlusionTexture: { index } }),
  emissive: (index: number) => ({ emissiveTexture: { index } }),
};

export function scene(options: SceneOptions): Scene {
  const blobs: Uint8Array[] = [];
  const views: { buffer: number; byteOffset: number; byteLength: number }[] = [];
  const resources: { pointer: string; image: { width: number; height: number } }[] = [];
  const images = options.images.map((image, index) => {
    let bytes: Uint8Array;
    let mimeType = "image/ktx2";
    if ("png" in image) {
      bytes = new Uint8Array(16);
      mimeType = "image/png";
      resources.push({ pointer: `/images/${index}`, image: image.png });
    } else {
      bytes = "ktx2" in image ? ktx2File(image.ktx2) : image.raw;
    }
    const offset = blobs.reduce((sum, blob) => sum + blob.byteLength, 0);
    views.push({ buffer: 0, byteOffset: offset, byteLength: bytes.byteLength });
    const padded = new Uint8Array(Math.ceil(bytes.byteLength / 4) * 4);
    padded.set(bytes);
    blobs.push(padded);
    return { bufferView: index, mimeType };
  });
  const bin = new Uint8Array(blobs.reduce((sum, blob) => sum + blob.byteLength, 0));
  let at = 0;
  for (const blob of blobs) {
    bin.set(blob, at);
    at += blob.byteLength;
  }
  const useExtension = (index: number): boolean => options.images[index] !== undefined && !("png" in options.images[index]!);
  const textures = options.images.map((_, index) =>
    useExtension(index) && options.plainSource !== true ? { extensions: { KHR_texture_basisu: { source: index } } } : { source: index },
  );
  const material: Record<string, unknown> = { name: "m", pbrMetallicRoughness: {} };
  for (const [slot, index] of Object.entries(options.slots ?? {})) {
    const reference = REFERENCES[slot]!(index);
    Object.assign(material, reference, { pbrMetallicRoughness: { ...(material.pbrMetallicRoughness as object), ...(reference.pbrMetallicRoughness ?? {}) } });
  }
  const anyKtx2 = options.images.some((_, index) => useExtension(index));
  const declare = options.declare ?? "both";
  const json: Record<string, unknown> = {
    asset: { version: "2.0" },
    materials: [material],
    textures,
    images,
    bufferViews: views,
    buffers: [{ byteLength: bin.byteLength }],
    ...(anyKtx2 && declare !== "none" ? { extensionsUsed: ["KHR_texture_basisu"] } : {}),
    ...(anyKtx2 && declare === "both" ? { extensionsRequired: ["KHR_texture_basisu"] } : {}),
  };
  const parts = parseGlb(buildGlb(json, bin));
  const analysis = analyse(parts.json);
  const info: ValidationInfo = { totalTriangleCount: 0, resources } as unknown as ValidationInfo;
  return { parts, analysis, info, images: readImages(parts, analysis, info) };
}
