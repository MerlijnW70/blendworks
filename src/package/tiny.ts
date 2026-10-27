import { buildGlb } from "./glb.js";

const PIXEL_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

export function tinyTexturedGlb(): Uint8Array {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  const uvs = new Float32Array([0, 0, 1, 0, 0, 1]);
  const indices = new Uint16Array([0, 1, 2, 0]);
  const parts = [new Uint8Array(positions.buffer), new Uint8Array(uvs.buffer), new Uint8Array(indices.buffer), new Uint8Array(PIXEL_PNG)];
  const views: { buffer: number; byteOffset: number; byteLength: number }[] = [];
  let offset = 0;
  const chunks: Uint8Array[] = [];
  for (const part of parts) {
    views.push({ buffer: 0, byteOffset: offset, byteLength: part.byteLength });
    const size = Math.ceil(part.byteLength / 4) * 4;
    const chunk = new Uint8Array(size);
    chunk.set(part);
    chunks.push(chunk);
    offset += size;
  }
  const bin = new Uint8Array(offset);
  let at = 0;
  for (const chunk of chunks) {
    bin.set(chunk, at);
    at += chunk.byteLength;
  }
  const json = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ name: "tiny", mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, TEXCOORD_0: 1 }, indices: 2, material: 0 }] }],
    materials: [{ name: "tiny", pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }],
    textures: [{ source: 0 }],
    images: [{ bufferView: 3, mimeType: "image/png" }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: "VEC3", min: [0, 0, 0], max: [1, 1, 0] },
      { bufferView: 1, componentType: 5126, count: 3, type: "VEC2" },
      { bufferView: 2, componentType: 5123, count: 3, type: "SCALAR" },
    ],
    bufferViews: views,
    buffers: [{ byteLength: bin.byteLength }],
  };
  return buildGlb(json, bin);
}
