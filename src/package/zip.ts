import { crc32, inflateRawSync } from "node:zlib";

const END_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;
const END_RECORD_BYTES = 22;
const MAX_COMMENT_BYTES = 0xffff;
const CENTRAL_HEADER_BYTES = 46;
const LOCAL_HEADER_BYTES = 30;
const STORED = 0;
const DEFLATED = 8;
const ENCRYPTED = 0x1;
const ZIP64_MARKER = 0xffffffff;

export class ZipError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ZipError";
  }
}

function endRecord(view: DataView): number {
  const earliest = Math.max(0, view.byteLength - END_RECORD_BYTES - MAX_COMMENT_BYTES);
  for (let at = view.byteLength - END_RECORD_BYTES; at >= earliest; at--) {
    if (view.getUint32(at, true) === END_SIGNATURE) return at;
  }
  throw new ZipError("the archive has no end-of-directory record");
}

export function readZipEntry(archive: Uint8Array, name: string, maxBytes: number): Uint8Array {
  if (archive.byteLength < END_RECORD_BYTES) throw new ZipError("the archive is too short to be a zip file");
  const view = new DataView(archive.buffer, archive.byteOffset, archive.byteLength);
  const end = endRecord(view);
  const entries = view.getUint16(end + 10, true);
  const directoryOffset = view.getUint32(end + 16, true);
  let at = directoryOffset;
  let found: Uint8Array | null = null;
  for (let index = 0; index < entries; index++) {
    if (at + CENTRAL_HEADER_BYTES > archive.byteLength || view.getUint32(at, true) !== CENTRAL_SIGNATURE) throw new ZipError("the archive directory is damaged");
    const flags = view.getUint16(at + 8, true);
    const method = view.getUint16(at + 10, true);
    const checksum = view.getUint32(at + 16, true);
    const compressed = view.getUint32(at + 20, true);
    const size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true);
    const extraLength = view.getUint16(at + 30, true);
    const commentLength = view.getUint16(at + 32, true);
    const localOffset = view.getUint32(at + 42, true);
    const entryName = new TextDecoder().decode(archive.subarray(at + CENTRAL_HEADER_BYTES, at + CENTRAL_HEADER_BYTES + nameLength));
    at += CENTRAL_HEADER_BYTES + nameLength + extraLength + commentLength;
    if (entryName !== name) continue;
    if (found !== null) throw new ZipError(`the archive holds ${name} twice`);
    if ((flags & ENCRYPTED) !== 0) throw new ZipError(`${name} is encrypted`);
    if (compressed === ZIP64_MARKER || size === ZIP64_MARKER || localOffset === ZIP64_MARKER) throw new ZipError(`${name} needs zip64, which is not supported`);
    if (size > maxBytes) throw new ZipError(`${name} unpacks to ${size} bytes, more than the ${maxBytes} allowed`);
    if (localOffset + LOCAL_HEADER_BYTES > archive.byteLength || view.getUint32(localOffset, true) !== LOCAL_SIGNATURE) throw new ZipError(`the header of ${name} is damaged`);
    const start = localOffset + LOCAL_HEADER_BYTES + view.getUint16(localOffset + 26, true) + view.getUint16(localOffset + 28, true);
    if (start + compressed > archive.byteLength) throw new ZipError(`${name} runs past the end of the archive`);
    const raw = archive.subarray(start, start + compressed);
    let data: Uint8Array;
    if (method === STORED) data = raw;
    else if (method === DEFLATED) data = inflateRawSync(raw, { maxOutputLength: Math.max(size, 1) });
    else throw new ZipError(`${name} uses compression method ${method}, which is not supported`);
    if (data.byteLength !== size) throw new ZipError(`${name} unpacks to ${data.byteLength} bytes, not the ${size} it declares`);
    if (crc32(data) !== checksum) throw new ZipError(`${name} fails its checksum`);
    found = new Uint8Array(data);
  }
  if (found === null) throw new ZipError(`the archive has no ${name}`);
  return found;
}
