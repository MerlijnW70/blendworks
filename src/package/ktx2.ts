export const KTX2_IDENTIFIER = Uint8Array.from([0xab, 0x4b, 0x54, 0x58, 0x20, 0x32, 0x30, 0xbb, 0x0d, 0x0a, 0x1a, 0x0a]);
export const KTX2_HEADER_BYTES = 80;
export const LEVEL_INDEX_ENTRY_BYTES = 24;
export const MAX_KTX2_LEVELS = 32;

export const SUPERCOMPRESSION = { none: 0, basisLz: 1, zstd: 2, zlib: 3 } as const;
export const COLOUR_MODEL = { etc1s: 0xa3, uastc: 0xa6 } as const;
export const TRANSFER_FUNCTION = { linear: 1, srgb: 2 } as const;

const BASIC_DESCRIPTOR_BYTES = 24;
const DFD_TOTAL_SIZE_BYTES = 4;
const BASIC_DESCRIPTOR_VERSION = 2;
const ALPHA_CHANNEL_ID = 15;
const SAMPLE_BYTES = 16;
const SAMPLE_CHANNEL_OFFSET = 3;

export type Ktx2Codec = "etc1s" | "uastc" | "other";
export type Ktx2Transfer = "srgb" | "linear" | "other";

export type Ktx2Level = { offset: number; bytes: number; uncompressedBytes: number };

export type Ktx2Info = {
  width: number;
  height: number;
  levelCount: number;
  layerCount: number;
  faceCount: number;
  vkFormat: number;
  supercompression: number;
  codec: Ktx2Codec;
  transfer: Ktx2Transfer;
  alpha: boolean;
  levels: Ktx2Level[];
};

export class Ktx2Error extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Ktx2Error";
  }
}

export function fullMipCount(width: number, height: number): number {
  return Math.floor(Math.log2(Math.max(width, height))) + 1;
}

function bigNumber(view: DataView, at: number, what: string): number {
  const value = view.getBigUint64(at, true);
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new Ktx2Error(`${what} is larger than any file`);
  return Number(value);
}

function inside(offset: number, length: number, total: number): boolean {
  return offset >= 0 && length >= 0 && offset + length <= total;
}

function codecOf(colourModel: number): Ktx2Codec {
  if (colourModel === COLOUR_MODEL.etc1s) return "etc1s";
  if (colourModel === COLOUR_MODEL.uastc) return "uastc";
  return "other";
}

function transferOf(function_: number): Ktx2Transfer {
  if (function_ === TRANSFER_FUNCTION.srgb) return "srgb";
  if (function_ === TRANSFER_FUNCTION.linear) return "linear";
  return "other";
}

function readDescriptor(view: DataView, offset: number, length: number): { codec: Ktx2Codec; transfer: Ktx2Transfer; alpha: boolean } {
  if (length < DFD_TOTAL_SIZE_BYTES + BASIC_DESCRIPTOR_BYTES) throw new Ktx2Error(`the data format descriptor is ${length} bytes, too short for a basic block`);
  if (view.getUint32(offset, true) !== length) throw new Ktx2Error("the data format descriptor declares a size that differs from its length in the header");
  const block = offset + DFD_TOTAL_SIZE_BYTES;
  const word0 = view.getUint32(block, true);
  const word1 = view.getUint32(block + 4, true);
  const vendor = word0 & 0x1ffff;
  const type = word0 >>> 17;
  const version = word1 & 0xffff;
  const blockBytes = word1 >>> 16;
  if (vendor !== 0 || type !== 0) throw new Ktx2Error("the first data format descriptor block is not a basic block");
  if (version !== BASIC_DESCRIPTOR_VERSION) throw new Ktx2Error(`the data format descriptor has version ${version}, not ${BASIC_DESCRIPTOR_VERSION}`);
  if (blockBytes < BASIC_DESCRIPTOR_BYTES || (blockBytes - BASIC_DESCRIPTOR_BYTES) % SAMPLE_BYTES !== 0 || DFD_TOTAL_SIZE_BYTES + blockBytes > length) {
    throw new Ktx2Error(`the basic descriptor block size ${blockBytes} does not fit the descriptor`);
  }
  const colourModel = view.getUint8(block + 8);
  const transfer = view.getUint8(block + 10);
  const samples = (blockBytes - BASIC_DESCRIPTOR_BYTES) / SAMPLE_BYTES;
  let alpha = false;
  for (let sample = 0; sample < samples; sample++) {
    const channel = view.getUint8(block + BASIC_DESCRIPTOR_BYTES + sample * SAMPLE_BYTES + SAMPLE_CHANNEL_OFFSET) & 0x0f;
    if (channel === ALPHA_CHANNEL_ID) alpha = true;
  }
  return { codec: codecOf(colourModel), transfer: transferOf(transfer), alpha };
}

export function parseKtx2(data: Uint8Array): Ktx2Info {
  if (data.byteLength < KTX2_HEADER_BYTES) throw new Ktx2Error(`the file is ${data.byteLength} bytes, shorter than the ${KTX2_HEADER_BYTES}-byte KTX2 header`);
  for (let index = 0; index < KTX2_IDENTIFIER.length; index++) {
    if (data[index] !== KTX2_IDENTIFIER[index]) throw new Ktx2Error("the file does not start with the KTX2 identifier");
  }
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const vkFormat = view.getUint32(12, true);
  const width = view.getUint32(20, true);
  const height = view.getUint32(24, true);
  const depth = view.getUint32(28, true);
  const layerCount = view.getUint32(32, true);
  const faceCount = view.getUint32(36, true);
  const declaredLevels = view.getUint32(40, true);
  const supercompression = view.getUint32(44, true);
  const dfdOffset = view.getUint32(48, true);
  const dfdLength = view.getUint32(52, true);
  const sgdOffset = bigNumber(view, 64, "the supercompression data offset");
  const sgdLength = bigNumber(view, 72, "the supercompression data length");
  if (width === 0 || height === 0) throw new Ktx2Error(`the size ${width} by ${height} is empty`);
  if (depth !== 0) throw new Ktx2Error(`the texture has depth ${depth}, but glTF textures are 2D`);
  if (faceCount !== 1) throw new Ktx2Error(`the texture has ${faceCount} faces, but glTF textures have one`);
  if (layerCount > 1) throw new Ktx2Error(`the texture has ${layerCount} layers, but glTF textures have one`);
  if (supercompression > SUPERCOMPRESSION.zlib) throw new Ktx2Error(`supercompression scheme ${supercompression} is unknown`);
  const levelCount = Math.max(declaredLevels, 1);
  if (levelCount > Math.min(fullMipCount(width, height), MAX_KTX2_LEVELS)) {
    throw new Ktx2Error(`${declaredLevels} mip levels cannot fit a ${width} by ${height} image (at most ${fullMipCount(width, height)})`);
  }
  const indexEnd = KTX2_HEADER_BYTES + levelCount * LEVEL_INDEX_ENTRY_BYTES;
  if (indexEnd > data.byteLength) throw new Ktx2Error(`the level index for ${levelCount} levels runs past the end of the file`);
  const levels: Ktx2Level[] = [];
  for (let level = 0; level < levelCount; level++) {
    const at = KTX2_HEADER_BYTES + level * LEVEL_INDEX_ENTRY_BYTES;
    const entry: Ktx2Level = { offset: bigNumber(view, at, `level ${level} offset`), bytes: bigNumber(view, at + 8, `level ${level} length`), uncompressedBytes: bigNumber(view, at + 16, `level ${level} uncompressed length`) };
    if (!inside(entry.offset, entry.bytes, data.byteLength) || entry.offset < indexEnd) throw new Ktx2Error(`mip level ${level} lies outside the file data`);
    levels.push(entry);
  }
  if (!inside(dfdOffset, dfdLength, data.byteLength)) throw new Ktx2Error("the data format descriptor lies outside the file");
  if (!inside(sgdOffset, sgdLength, data.byteLength)) throw new Ktx2Error("the supercompression global data lies outside the file");
  const descriptor = readDescriptor(view, dfdOffset, dfdLength);
  if (descriptor.codec === "etc1s" && supercompression !== SUPERCOMPRESSION.basisLz) throw new Ktx2Error("an ETC1S texture must use BasisLZ supercompression");
  return { width, height, levelCount, layerCount: Math.max(layerCount, 1), faceCount, vkFormat, supercompression, levels, ...descriptor };
}
