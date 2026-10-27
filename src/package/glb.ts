export const GLB_MAGIC = 0x46546c67;
const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;

export type GlbParts = { json: Record<string, unknown>; bin: Uint8Array | null };

export class GlbError extends Error {}

export function parseGlb(data: Uint8Array): GlbParts {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  if (data.byteLength < 20 || view.getUint32(0, true) !== GLB_MAGIC || view.getUint32(4, true) !== 2) throw new GlbError("not a glTF 2.0 binary");
  const declared = Math.min(view.getUint32(8, true), data.byteLength);
  let json: Record<string, unknown> | null = null;
  let bin: Uint8Array | null = null;
  let offset = 12;
  while (offset + 8 <= declared) {
    const length = view.getUint32(offset, true);
    const type = view.getUint32(offset + 4, true);
    const start = offset + 8;
    if (start + length > declared) throw new GlbError("a glTF chunk runs past the end of the file");
    if (type === JSON_CHUNK && json === null) {
      json = JSON.parse(new TextDecoder().decode(data.subarray(start, start + length))) as Record<string, unknown>;
    } else if (type === BIN_CHUNK && bin === null) {
      bin = data.subarray(start, start + length);
    }
    offset = start + length + ((4 - (length % 4)) % 4);
  }
  if (json === null) throw new GlbError("the glTF binary has no JSON chunk");
  return { json, bin };
}

function padded(bytes: Uint8Array, fill: number): Uint8Array {
  const size = Math.ceil(bytes.byteLength / 4) * 4;
  const out = new Uint8Array(size).fill(fill);
  out.set(bytes);
  return out;
}

export function buildGlb(json: Record<string, unknown>, bin: Uint8Array | null): Uint8Array {
  const jsonBytes = padded(new TextEncoder().encode(JSON.stringify(json)), 0x20);
  const binBytes = bin === null ? null : padded(bin, 0);
  const total = 12 + 8 + jsonBytes.byteLength + (binBytes === null ? 0 : 8 + binBytes.byteLength);
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, GLB_MAGIC, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonBytes.byteLength, true);
  view.setUint32(16, JSON_CHUNK, true);
  out.set(jsonBytes, 20);
  if (binBytes !== null) {
    const at = 20 + jsonBytes.byteLength;
    view.setUint32(at, binBytes.byteLength, true);
    view.setUint32(at + 4, BIN_CHUNK, true);
    out.set(binBytes, at + 8);
  }
  return out;
}
