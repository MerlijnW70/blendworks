import { COLOUR_MODEL, KTX2_HEADER_BYTES, KTX2_IDENTIFIER, LEVEL_INDEX_ENTRY_BYTES, SUPERCOMPRESSION, TRANSFER_FUNCTION, fullMipCount, type Ktx2Codec, type Ktx2Transfer } from "../../src/package/ktx2.js";

export type Ktx2Fixture = {
  width: number;
  height: number;
  levels?: number;
  codec?: Ktx2Codec;
  transfer?: Ktx2Transfer;
  alpha?: boolean;
  supercompression?: number;
  payloadBytes?: number;
};

const DFD_BLOCK_BYTES = 24;
const SAMPLE_BYTES = 16;

function descriptor(codec: Ktx2Codec, transfer: Ktx2Transfer, alpha: boolean): Uint8Array {
  const samples = codec === "etc1s" && alpha ? 2 : 1;
  const blockBytes = DFD_BLOCK_BYTES + samples * SAMPLE_BYTES;
  const out = new Uint8Array(4 + blockBytes);
  const view = new DataView(out.buffer);
  view.setUint32(0, out.byteLength, true);
  view.setUint32(4, 0, true);
  view.setUint32(8, 2 | (blockBytes << 16), true);
  view.setUint8(12, codec === "etc1s" ? COLOUR_MODEL.etc1s : codec === "uastc" ? COLOUR_MODEL.uastc : 1);
  view.setUint8(13, 1);
  view.setUint8(14, transfer === "srgb" ? TRANSFER_FUNCTION.srgb : TRANSFER_FUNCTION.linear);
  view.setUint8(15, alpha ? 1 : 0);
  view.setUint8(16, 3);
  view.setUint8(17, 3);
  for (let sample = 0; sample < samples; sample++) view.setUint8(4 + DFD_BLOCK_BYTES + sample * SAMPLE_BYTES + 3, sample === 1 ? 15 : 0);
  return out;
}

export function ktx2File(fixture: Ktx2Fixture): Uint8Array {
  const { width, height } = fixture;
  const levels = fixture.levels ?? fullMipCount(width, height);
  const codec = fixture.codec ?? "uastc";
  const supercompression = fixture.supercompression ?? (codec === "etc1s" ? SUPERCOMPRESSION.basisLz : SUPERCOMPRESSION.zstd);
  const dfd = descriptor(codec, fixture.transfer ?? "linear", fixture.alpha === true);
  const indexEnd = KTX2_HEADER_BYTES + Math.max(levels, 1) * LEVEL_INDEX_ENTRY_BYTES;
  const payload = fixture.payloadBytes ?? 64;
  const dfdOffset = indexEnd;
  const dataOffset = Math.ceil((dfdOffset + dfd.byteLength) / 8) * 8;
  const out = new Uint8Array(dataOffset + payload * Math.max(levels, 1));
  const view = new DataView(out.buffer);
  out.set(KTX2_IDENTIFIER, 0);
  view.setUint32(12, 0, true);
  view.setUint32(16, 1, true);
  view.setUint32(20, width, true);
  view.setUint32(24, height, true);
  view.setUint32(28, 0, true);
  view.setUint32(32, 0, true);
  view.setUint32(36, 1, true);
  view.setUint32(40, levels, true);
  view.setUint32(44, supercompression, true);
  view.setUint32(48, dfdOffset, true);
  view.setUint32(52, dfd.byteLength, true);
  out.set(dfd, dfdOffset);
  for (let level = 0; level < Math.max(levels, 1); level++) {
    const at = KTX2_HEADER_BYTES + level * LEVEL_INDEX_ENTRY_BYTES;
    view.setBigUint64(at, BigInt(dataOffset + level * payload), true);
    view.setBigUint64(at + 8, BigInt(payload), true);
    view.setBigUint64(at + 16, BigInt(payload * 2), true);
  }
  return out;
}

export function withField(bytes: Uint8Array, offset: number, value: number, size: 1 | 4 = 4): Uint8Array {
  const copy = bytes.slice();
  const view = new DataView(copy.buffer);
  if (size === 4) view.setUint32(offset, value, true);
  else view.setUint8(offset, value);
  return copy;
}
