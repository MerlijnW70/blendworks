import { buildGlb } from "../../src/package/glb.js";
import { normalPng, paintedPng } from "./png.js";

export const TEXTURED_SIZE = { width: 96, height: 64 } as const;
export const TEXTURED_MIP_LEVELS = 7;

type MapKind = "baseColor" | "normal" | "metallicRoughness" | "occlusion" | "emissive";

export type TexturedMaterial = { name: string; maps: MapKind[]; alpha?: boolean };

export const DEFAULT_MATERIALS: TexturedMaterial[] = [
  { name: "painted", maps: ["baseColor", "normal", "metallicRoughness"] },
  { name: "glass", maps: ["baseColor", "emissive"], alpha: true },
];

function padded(bytes: Uint8Array): Uint8Array {
  const out = new Uint8Array(Math.ceil(bytes.byteLength / 4) * 4);
  out.set(bytes);
  return out;
}

function imageFor(kind: MapKind, seed: number, alpha: boolean): Uint8Array {
  const { width, height } = TEXTURED_SIZE;
  return kind === "normal" ? normalPng(width, height) : paintedPng(width, height, seed, alpha && kind === "baseColor");
}

export function texturedGlb(materials: TexturedMaterial[] = DEFAULT_MATERIALS): Uint8Array {
  const blobs: Uint8Array[] = [];
  const views: { buffer: number; byteOffset: number; byteLength: number }[] = [];
  const add = (bytes: Uint8Array): number => {
    const offset = blobs.reduce((sum, blob) => sum + blob.byteLength, 0);
    views.push({ buffer: 0, byteOffset: offset, byteLength: bytes.byteLength });
    blobs.push(padded(bytes));
    return views.length - 1;
  };
  const accessors: Record<string, unknown>[] = [];
  const primitives: Record<string, unknown>[] = [];
  const gltfMaterials: Record<string, unknown>[] = [];
  const textures: Record<string, unknown>[] = [];
  const images: Record<string, unknown>[] = [];
  materials.forEach((material, index) => {
    const x = index * 2;
    const positions = new Float32Array([x, 0, 0, x + 1, 0, 0, x + 1, 1, 0, x, 1, 0]);
    const uvs = new Float32Array([0, 1, 1, 1, 1, 0, 0, 0]);
    const indices = new Uint16Array([0, 1, 2, 0, 2, 3]);
    const positionAccessor = accessors.push({ bufferView: add(new Uint8Array(positions.buffer)), componentType: 5126, count: 4, type: "VEC3", min: [x, 0, 0], max: [x + 1, 1, 0] }) - 1;
    const uvAccessor = accessors.push({ bufferView: add(new Uint8Array(uvs.buffer)), componentType: 5126, count: 4, type: "VEC2" }) - 1;
    const indexAccessor = accessors.push({ bufferView: add(new Uint8Array(indices.buffer)), componentType: 5123, count: 6, type: "SCALAR" }) - 1;
    primitives.push({ attributes: { POSITION: positionAccessor, TEXCOORD_0: uvAccessor }, indices: indexAccessor, material: index });
    const slot = (kind: MapKind): { index: number } => {
      images.push({ name: `${material.name}_${kind}`, bufferView: add(imageFor(kind, 17 * (images.length + 1), material.alpha === true)), mimeType: "image/png" });
      textures.push({ source: images.length - 1 });
      return { index: textures.length - 1 };
    };
    const entry: Record<string, unknown> = { name: material.name, ...(material.alpha === true ? { alphaMode: "BLEND" } : {}) };
    const pbr: Record<string, unknown> = {};
    if (material.maps.includes("baseColor")) pbr.baseColorTexture = slot("baseColor");
    if (material.maps.includes("metallicRoughness")) pbr.metallicRoughnessTexture = slot("metallicRoughness");
    if (Object.keys(pbr).length > 0) entry.pbrMetallicRoughness = pbr;
    if (material.maps.includes("normal")) entry.normalTexture = slot("normal");
    if (material.maps.includes("occlusion")) entry.occlusionTexture = slot("occlusion");
    if (material.maps.includes("emissive")) {
      entry.emissiveTexture = slot("emissive");
      entry.emissiveFactor = [1, 1, 1];
    }
    gltfMaterials.push(entry);
  });
  const bin = new Uint8Array(blobs.reduce((sum, blob) => sum + blob.byteLength, 0));
  let at = 0;
  for (const blob of blobs) {
    bin.set(blob, at);
    at += blob.byteLength;
  }
  const json = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ name: "textured", mesh: 0 }],
    meshes: [{ primitives }],
    materials: gltfMaterials,
    textures,
    images,
    accessors,
    bufferViews: views,
    buffers: [{ byteLength: bin.byteLength }],
  };
  return buildGlb(json, bin);
}
