import { gunzipSync, zstdDecompressSync } from "node:zlib";

export const MAX_BLEND_BYTES = 1024 * 1024 * 1024;

export type BlendReferenceKind = "library" | "image" | "movieclip" | "sound" | "volume" | "cachefile" | "font";

export type BlendReference = { kind: BlendReferenceKind; name: string; path: string };

export class BlendScanError extends Error {}

type Layout = { pointer: 4 | 8; little: boolean; headerBytes: number; bhead: "small" | "large" };

type Block = { code: string; start: number; length: number; sdna: number; count: number };

type Field = { type: string; name: string; offset: number; size: number };

type Dna = { pointer: number; structs: Map<number, { name: string; size: number; fields: Map<string, Field> }> };

const ZSTD_MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
const GZIP_MAGIC = Buffer.from([0x1f, 0x8b]);
const SEEK_TABLE_MAGIC = 0x8f92eab1;

const BLOCKS: Record<string, { kind: BlendReferenceKind; struct: string; packed: string[] }> = {
  LI: { kind: "library", struct: "Library", packed: ["packedfile"] },
  IM: { kind: "image", struct: "Image", packed: ["packedfiles", "packedfile"] },
  MC: { kind: "movieclip", struct: "MovieClip", packed: [] },
  SO: { kind: "sound", struct: "bSound", packed: ["packedfile"] },
  VO: { kind: "volume", struct: "Volume", packed: ["packedfile"] },
  CF: { kind: "cachefile", struct: "CacheFile", packed: [] },
  VF: { kind: "font", struct: "VFont", packed: ["packedfile"] },
};

const IMAGE_SOURCES_FROM_DISK = new Set([1, 2, 3, 6]);
const BUILTIN_FONT = "<builtin>";

function zstdFrames(data: Buffer): Buffer[] {
  const footer = data.length - 9;
  if (footer < 8 || data.readUInt32LE(footer + 5) !== SEEK_TABLE_MAGIC) return [data];
  const frames = data.readUInt32LE(footer);
  const entryBytes = (data[footer + 4]! & 0x80) === 0 ? 8 : 12;
  const table = footer - frames * entryBytes;
  if (frames === 0 || table < 8) throw new BlendScanError("the compressed .blend has a damaged seek table");
  const parts: Buffer[] = [];
  let at = 0;
  for (let index = 0; index < frames; index += 1) {
    const compressed = data.readUInt32LE(table + index * entryBytes);
    if (at + compressed > table - 8) throw new BlendScanError("the compressed .blend has a frame that runs past its seek table");
    parts.push(data.subarray(at, at + compressed));
    at += compressed;
  }
  return parts;
}

function inflate(data: Buffer): Buffer {
  try {
    if (data.subarray(0, 4).equals(ZSTD_MAGIC)) {
      const parts: Buffer[] = [];
      let total = 0;
      for (const frame of zstdFrames(data)) {
        const part = zstdDecompressSync(frame, { maxOutputLength: MAX_BLEND_BYTES - total });
        total += part.length;
        parts.push(part);
      }
      return Buffer.concat(parts);
    }
    if (data.subarray(0, 2).equals(GZIP_MAGIC)) return gunzipSync(data, { maxOutputLength: MAX_BLEND_BYTES });
  } catch (error) {
    if (error instanceof BlendScanError) throw error;
    throw new BlendScanError(`the compressed .blend cannot be unpacked for its file references: ${(error as Error).message}`);
  }
  return data;
}

function layoutOf(data: Buffer): Layout {
  if (data.length < 12 || data.toString("latin1", 0, 7) !== "BLENDER") throw new BlendScanError("the file has no .blend header");
  const legacy = data.toString("latin1", 7, 8);
  if (legacy === "_" || legacy === "-") {
    const endian = data.toString("latin1", 8, 9);
    if (endian !== "v" && endian !== "V") throw new BlendScanError("the .blend header names no byte order");
    return { pointer: legacy === "_" ? 4 : 8, little: endian === "v", headerBytes: 12, bhead: "small" };
  }
  const header = /^(\d\d)([-_])(\d\d)([vV])(\d{4})$/.exec(data.toString("latin1", 7, 17));
  if (header === null || header[1] !== "17" || header[3] !== "01") throw new BlendScanError("the .blend header has a format the judge does not know");
  return { pointer: header[2] === "_" ? 4 : 8, little: header[4] === "v", headerBytes: 17, bhead: "large" };
}

class Bytes {
  constructor(
    readonly data: Buffer,
    readonly little: boolean,
  ) {}

  u16(at: number): number {
    return this.little ? this.data.readUInt16LE(at) : this.data.readUInt16BE(at);
  }

  u32(at: number): number {
    return this.little ? this.data.readUInt32LE(at) : this.data.readUInt32BE(at);
  }

  u64(at: number): number {
    const value = this.little ? this.data.readBigUInt64LE(at) : this.data.readBigUInt64BE(at);
    if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new BlendScanError("the .blend has a block length out of range");
    return Number(value);
  }

  pointer(at: number, size: number): boolean {
    if (size === 4) return this.u32(at) !== 0;
    return (this.little ? this.data.readBigUInt64LE(at) : this.data.readBigUInt64BE(at)) !== 0n;
  }
}

function blocks(bytes: Bytes, layout: Layout): Block[] {
  const found: Block[] = [];
  const size = bytes.data.length;
  const headBytes = layout.bhead === "large" ? 32 : 16 + layout.pointer;
  let at = layout.headerBytes;
  while (at + headBytes <= size) {
    const code = bytes.data.toString("latin1", at, at + 4).replace(/\0+$/, "");
    if (code === "ENDB") return found;
    let block: Block;
    if (layout.bhead === "large") {
      block = { code, sdna: bytes.u32(at + 4), length: bytes.u64(at + 16), count: bytes.u64(at + 24), start: at + 32 };
    } else {
      block = { code, length: bytes.u32(at + 4), sdna: bytes.u32(at + 8 + layout.pointer), count: bytes.u32(at + 12 + layout.pointer), start: at + headBytes };
    }
    if (block.start + block.length > size) throw new BlendScanError("the .blend has a block that runs past the end of the file");
    found.push(block);
    at = block.start + block.length;
  }
  throw new BlendScanError("the .blend ends before its end block");
}

function aligned(at: number, base: number): number {
  return base + ((at - base + 3) & ~3);
}

function strings(data: Buffer, at: number, count: number, end: number, base: number): { values: string[]; next: number } {
  const values: string[] = [];
  let position = at;
  for (let index = 0; index < count; index += 1) {
    const stop = data.indexOf(0, position);
    if (stop === -1 || stop >= end) throw new BlendScanError("the .blend type table is damaged");
    values.push(data.toString("latin1", position, stop));
    position = stop + 1;
  }
  return { values, next: aligned(position, base) };
}

function fieldSize(name: string, typeSize: number, pointer: number): { base: string; size: number } {
  const dimensions = [...name.matchAll(/\[(\d+)\]/g)].reduce((product, match) => product * Number(match[1]), 1);
  const isPointer = name.startsWith("*") || name.startsWith("(*");
  const base = name.replace(/\[\d+\]/g, "").replace(/^[(*]+/, "").replace(/\).*$/, "");
  return { base, size: (isPointer ? pointer : typeSize) * dimensions };
}

function tag(bytes: Bytes, at: number, expected: string): void {
  if (bytes.data.toString("latin1", at, at + 4) !== expected) throw new BlendScanError(`the .blend type table has no ${expected} section`);
}

function readDna(bytes: Bytes, block: Block, pointer: number): Dna {
  const end = block.start + block.length;
  tag(bytes, block.start, "SDNA");
  tag(bytes, block.start + 4, "NAME");
  const names = strings(bytes.data, block.start + 12, bytes.u32(block.start + 8), end, block.start);
  tag(bytes, names.next, "TYPE");
  const types = strings(bytes.data, names.next + 8, bytes.u32(names.next + 4), end, block.start);
  tag(bytes, types.next, "TLEN");
  const lengths = types.values.map((_, index) => bytes.u16(types.next + 4 + 2 * index));
  let at = aligned(types.next + 4 + 2 * types.values.length, block.start);
  tag(bytes, at, "STRC");
  const count = bytes.u32(at + 4);
  at += 8;
  const structs: Dna["structs"] = new Map();
  for (let index = 0; index < count; index += 1) {
    if (at + 4 > end) throw new BlendScanError("the .blend type table is damaged");
    const typeIndex = bytes.u16(at);
    const fieldCount = bytes.u16(at + 2);
    at += 4;
    const fields = new Map<string, Field>();
    let offset = 0;
    for (let field = 0; field < fieldCount; field += 1) {
      const fieldType = bytes.u16(at);
      const fieldName = names.values[bytes.u16(at + 2)] ?? "";
      at += 4;
      const { base, size } = fieldSize(fieldName, lengths[fieldType] ?? 0, pointer);
      if (!fields.has(base)) fields.set(base, { type: types.values[fieldType] ?? "", name: fieldName, offset, size });
      offset += size;
    }
    structs.set(index, { name: types.values[typeIndex] ?? "", size: lengths[typeIndex] ?? offset, fields });
  }
  return { pointer, structs };
}

function text(data: Buffer, at: number, size: number): string {
  const slice = data.subarray(at, at + size);
  const stop = slice.indexOf(0);
  return slice.subarray(0, stop === -1 ? slice.length : stop).toString("utf8");
}

function reference(bytes: Bytes, dna: Dna, block: Block): BlendReference | null {
  const known = BLOCKS[block.code];
  if (known === undefined) return null;
  const struct = dna.structs.get(block.sdna);
  if (struct === undefined || struct.name !== known.struct) throw new BlendScanError(`the .blend has a ${block.code} block that is not a ${known.struct}`);
  const filepath = struct.fields.get("filepath") ?? struct.fields.get("name");
  const id = struct.fields.get("id");
  const idStruct = id === undefined ? undefined : [...dna.structs.values()].find((entry) => entry.name === id.type);
  const idName = idStruct?.fields.get("name");
  if (filepath === undefined || filepath.offset + filepath.size > block.length) throw new BlendScanError(`the .blend ${known.struct} has no file path field`);
  const path = text(bytes.data, block.start + filepath.offset, filepath.size);
  const name = id !== undefined && idName !== undefined ? text(bytes.data, block.start + id.offset + idName.offset, idName.size).slice(2) : "";
  for (const packed of known.packed) {
    const field = struct.fields.get(packed);
    if (field !== undefined && bytes.pointer(block.start + field.offset, dna.pointer)) return null;
  }
  if (path === "") return null;
  if (known.kind === "font" && path === BUILTIN_FONT) return null;
  if (known.kind === "image") {
    const source = struct.fields.get("source");
    if (source !== undefined && !IMAGE_SOURCES_FROM_DISK.has(bytes.u16(block.start + source.offset))) return null;
  }
  return { kind: known.kind, name, path };
}

export function blendReferences(file: Buffer): BlendReference[] {
  const data = inflate(file);
  const layout = layoutOf(data);
  const bytes = new Bytes(data, layout.little);
  const all = blocks(bytes, layout);
  const dnaBlock = all.find((block) => block.code === "DNA1");
  if (dnaBlock === undefined) throw new BlendScanError("the .blend has no type table");
  const dna = readDna(bytes, dnaBlock, layout.pointer);
  return all.flatMap((block) => {
    const found = reference(bytes, dna, block);
    return found === null ? [] : [found];
  });
}
