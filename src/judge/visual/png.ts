import { crc32, deflateSync, inflateSync } from "node:zlib";

export const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
export const MAX_PNG_SIDE = 16384;

export type Pixels = { width: number; height: number; rgba: Uint8Array };

export class PngError extends Error {}

const CHANNELS: Record<number, number> = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 };

type Header = { width: number; height: number; depth: number; colourType: number };

function readChunks(data: Buffer): { header: Header; palette: Buffer | null; transparency: Buffer | null; idat: Buffer } {
  if (data.length < 8 || !data.subarray(0, 8).equals(PNG_SIGNATURE)) throw new PngError("not a PNG file");
  let offset = 8;
  let header: Header | null = null;
  let palette: Buffer | null = null;
  let transparency: Buffer | null = null;
  const idat: Buffer[] = [];
  while (offset + 12 <= data.length) {
    const length = data.readUInt32BE(offset);
    const type = data.toString("latin1", offset + 4, offset + 8);
    const end = offset + 12 + length;
    if (end > data.length) throw new PngError("a PNG chunk runs past the end of the file");
    const body = data.subarray(offset + 8, offset + 8 + length);
    if (crc32(data.subarray(offset + 4, offset + 8 + length)) !== data.readUInt32BE(offset + 8 + length)) throw new PngError(`the PNG chunk ${type} has a bad checksum`);
    if (type === "IHDR") {
      if (body[10] !== 0 || body[11] !== 0) throw new PngError("unsupported PNG compression or filter method");
      if (body[12] !== 0) throw new PngError("interlaced PNG files are not supported");
      header = { width: body.readUInt32BE(0), height: body.readUInt32BE(4), depth: body[8]!, colourType: body[9]! };
    } else if (type === "PLTE") palette = body;
    else if (type === "tRNS") transparency = body;
    else if (type === "IDAT") idat.push(body);
    else if (type === "IEND") break;
    offset = end;
  }
  if (header === null) throw new PngError("the PNG has no header");
  return { header, palette, transparency, idat: Buffer.concat(idat) };
}

function checkHeader(header: Header): number {
  const channels = CHANNELS[header.colourType];
  if (channels === undefined) throw new PngError(`unsupported PNG colour type ${header.colourType}`);
  const depths = header.colourType === 3 ? [1, 2, 4, 8] : header.colourType === 0 ? [1, 2, 4, 8, 16] : [8, 16];
  if (!depths.includes(header.depth)) throw new PngError(`unsupported PNG bit depth ${header.depth}`);
  if (header.width < 1 || header.height < 1 || header.width > MAX_PNG_SIDE || header.height > MAX_PNG_SIDE) throw new PngError(`the PNG is ${header.width} x ${header.height}, at most ${MAX_PNG_SIDE} on a side`);
  return channels;
}

function paeth(left: number, up: number, upLeft: number): number {
  const estimate = left + up - upLeft;
  const toLeft = Math.abs(estimate - left);
  const toUp = Math.abs(estimate - up);
  const toUpLeft = Math.abs(estimate - upLeft);
  if (toLeft <= toUp && toLeft <= toUpLeft) return left;
  return toUp <= toUpLeft ? up : upLeft;
}

function unfilter(raw: Buffer, rowBytes: number, height: number, step: number): Uint8Array {
  if (raw.length < (rowBytes + 1) * height) throw new PngError("the PNG image data is truncated");
  const out = new Uint8Array(rowBytes * height);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (rowBytes + 1)]!;
    const source = y * (rowBytes + 1) + 1;
    const row = y * rowBytes;
    for (let x = 0; x < rowBytes; x += 1) {
      const value = raw[source + x]!;
      const left = x >= step ? out[row + x - step]! : 0;
      const up = y > 0 ? out[row - rowBytes + x]! : 0;
      const upLeft = x >= step && y > 0 ? out[row - rowBytes + x - step]! : 0;
      let predicted: number;
      if (filter === 0) predicted = 0;
      else if (filter === 1) predicted = left;
      else if (filter === 2) predicted = up;
      else if (filter === 3) predicted = (left + up) >> 1;
      else if (filter === 4) predicted = paeth(left, up, upLeft);
      else throw new PngError(`unknown PNG row filter ${filter}`);
      out[row + x] = (value + predicted) & 0xff;
    }
  }
  return out;
}

function sample(data: Uint8Array, rowStart: number, index: number, depth: number): number {
  if (depth === 8) return data[rowStart + index]!;
  if (depth === 16) return data[rowStart + index * 2]!;
  const perByte = 8 / depth;
  const byte = data[rowStart + Math.floor(index / perByte)]!;
  const shift = 8 - depth * ((index % perByte) + 1);
  return (byte >> shift) & ((1 << depth) - 1);
}

export function decodePng(data: Buffer): Pixels {
  const { header, palette, transparency, idat } = readChunks(data);
  const channels = checkHeader(header);
  const { width, height, depth, colourType } = header;
  const rowBytes = Math.ceil((width * channels * depth) / 8);
  let raw: Buffer;
  try {
    raw = inflateSync(idat, { maxOutputLength: (rowBytes + 1) * height + 1 });
  } catch {
    throw new PngError("the PNG image data does not inflate");
  }
  const rows = unfilter(raw, rowBytes, height, Math.max(1, Math.ceil((channels * depth) / 8)));
  const rgba = new Uint8Array(width * height * 4);
  const scale = depth < 8 ? 255 / ((1 << depth) - 1) : 1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const at = (y * width + x) * 4;
      const value = (channel: number) => sample(rows, y * rowBytes, x * channels + channel, depth);
      if (colourType === 3) {
        const index = value(0);
        if (palette === null || index * 3 + 2 >= palette.length) throw new PngError("a PNG palette index is out of range");
        rgba.set([palette[index * 3]!, palette[index * 3 + 1]!, palette[index * 3 + 2]!, transparency?.[index] ?? 255], at);
      } else if (colourType === 0 || colourType === 4) {
        const grey = Math.round(value(0) * scale);
        rgba.set([grey, grey, grey, colourType === 4 ? value(1) : 255], at);
      } else {
        rgba.set([value(0), value(1), value(2), colourType === 6 ? value(3) : 255], at);
      }
    }
  }
  return { width, height, rgba };
}

const TO_LINEAR = Float64Array.from({ length: 256 }, (_, value) => {
  const unit = value / 255;
  return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
});

function toSrgb(linear: number): number {
  const clamped = Math.min(1, Math.max(0, linear));
  const unit = clamped <= 0.0031308 ? clamped * 12.92 : 1.055 * clamped ** (1 / 2.4) - 0.055;
  return Math.round(unit * 255);
}

export function fitWithin(width: number, height: number, cap: number): { width: number; height: number } {
  const longest = Math.max(width, height);
  if (longest <= cap) return { width, height };
  const ratio = cap / longest;
  return { width: Math.max(1, Math.round(width * ratio)), height: Math.max(1, Math.round(height * ratio)) };
}

function spans(source: number, target: number): { start: number; weights: number[] }[] {
  const ratio = source / target;
  return Array.from({ length: target }, (_, index) => {
    const from = index * ratio;
    const to = from + ratio;
    const start = Math.floor(from);
    const weights: number[] = [];
    for (let at = start; at < Math.min(source, Math.ceil(to)); at += 1) weights.push(Math.min(to, at + 1) - Math.max(from, at));
    return { start, weights };
  });
}

export function downscale(image: Pixels, width: number, height: number): Pixels {
  if (width === image.width && height === image.height) return image;
  const columns = spans(image.width, width);
  const rows = spans(image.height, height);
  const rgba = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    const row = rows[y]!;
    for (let x = 0; x < width; x += 1) {
      const column = columns[x]!;
      let red = 0;
      let green = 0;
      let blue = 0;
      let alpha = 0;
      let area = 0;
      row.weights.forEach((rowWeight, dy) => {
        column.weights.forEach((columnWeight, dx) => {
          const weight = rowWeight * columnWeight;
          const at = ((row.start + dy) * image.width + column.start + dx) * 4;
          const opacity = image.rgba[at + 3]! / 255;
          red += TO_LINEAR[image.rgba[at]!]! * opacity * weight;
          green += TO_LINEAR[image.rgba[at + 1]!]! * opacity * weight;
          blue += TO_LINEAR[image.rgba[at + 2]!]! * opacity * weight;
          alpha += opacity * weight;
          area += weight;
        });
      });
      const at = (y * width + x) * 4;
      const cover = alpha > 0 ? alpha : 1;
      rgba.set([toSrgb(red / cover), toSrgb(green / cover), toSrgb(blue / cover), Math.round((alpha / area) * 255)], at);
    }
  }
  return { width, height, rgba };
}

function chunk(type: string, body: Buffer): Buffer {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(body.length, 0);
  head.write(type, 4, "latin1");
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), body])), 0);
  return Buffer.concat([head, body, tail]);
}

function filteredRows(image: Pixels, channels: number): Buffer {
  const rowBytes = image.width * channels;
  const out = Buffer.alloc((rowBytes + 1) * image.height);
  const packed = new Uint8Array(rowBytes * image.height);
  for (let index = 0; index < image.width * image.height; index += 1) {
    for (let channel = 0; channel < channels; channel += 1) packed[index * channels + channel] = image.rgba[index * 4 + channel]!;
  }
  const candidate = new Uint8Array(rowBytes);
  for (let y = 0; y < image.height; y += 1) {
    const row = y * rowBytes;
    const best = { filter: 0, cost: Infinity, bytes: new Uint8Array(rowBytes) };
    for (let filter = 0; filter <= 4; filter += 1) {
      let cost = 0;
      for (let x = 0; x < rowBytes; x += 1) {
        const left = x >= channels ? packed[row + x - channels]! : 0;
        const up = y > 0 ? packed[row - rowBytes + x]! : 0;
        const upLeft = x >= channels && y > 0 ? packed[row - rowBytes + x - channels]! : 0;
        const predicted = filter === 0 ? 0 : filter === 1 ? left : filter === 2 ? up : filter === 3 ? (left + up) >> 1 : paeth(left, up, upLeft);
        const value = (packed[row + x]! - predicted) & 0xff;
        candidate[x] = value;
        cost += value < 128 ? value : 256 - value;
      }
      if (cost < best.cost) {
        best.filter = filter;
        best.cost = cost;
        best.bytes.set(candidate);
      }
    }
    out[y * (rowBytes + 1)] = best.filter;
    out.set(best.bytes, y * (rowBytes + 1) + 1);
  }
  return out;
}

export function encodePng(image: Pixels): Buffer {
  let opaque = true;
  for (let index = 3; index < image.rgba.length; index += 4) if (image.rgba[index] !== 255) opaque = false;
  const channels = opaque ? 3 : 4;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(image.width, 0);
  header.writeUInt32BE(image.height, 4);
  header.set([8, opaque ? 2 : 6, 0, 0, 0], 8);
  const data = deflateSync(filteredRows(image, channels), { level: 9 });
  return Buffer.concat([PNG_SIGNATURE, chunk("IHDR", header), chunk("IDAT", data), chunk("IEND", Buffer.alloc(0))]);
}
