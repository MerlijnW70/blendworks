import { crc32, deflateSync } from "node:zlib";

const SIGNATURE = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const COLOUR_TYPE_RGB = 2;
const COLOUR_TYPE_RGBA = 6;

export type Pixel = [number, number, number, number];

function chunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.byteLength);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.byteLength);
  out.set(new TextEncoder().encode(type), 4);
  out.set(data, 8);
  view.setUint32(8 + data.byteLength, crc32(out.subarray(4, 8 + data.byteLength)));
  return out;
}

export function encodePng(width: number, height: number, pixel: (x: number, y: number) => Pixel, alpha: boolean): Uint8Array {
  const channels = alpha ? 4 : 3;
  const raw = new Uint8Array(height * (1 + width * channels));
  let at = 0;
  for (let y = 0; y < height; y++) {
    raw[at++] = 0;
    for (let x = 0; x < width; x++) {
      const [r, g, b, a] = pixel(x, y);
      raw[at++] = r;
      raw[at++] = g;
      raw[at++] = b;
      if (alpha) raw[at++] = a;
    }
  }
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  header[8] = 8;
  header[9] = alpha ? COLOUR_TYPE_RGBA : COLOUR_TYPE_RGB;
  const parts = [SIGNATURE, chunk("IHDR", header), chunk("IDAT", deflateSync(raw)), chunk("IEND", new Uint8Array(0))];
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.byteLength, 0));
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.byteLength;
  }
  return out;
}

function noise(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

export function paintedPng(width: number, height: number, seed: number, alpha = false): Uint8Array {
  const random = noise(seed);
  return encodePng(
    width,
    height,
    (x, y) => [
      Math.round(255 * (x / width)),
      Math.round(255 * (y / height)),
      Math.round(128 + 100 * Math.sin((x + y) / 7) + 20 * random()) & 255,
      alpha ? (x < width / 2 ? 255 : 90) : 255,
    ],
    alpha,
  );
}

export function normalPng(width: number, height: number): Uint8Array {
  return encodePng(
    width,
    height,
    (x, y) => {
      const nx = 0.35 * Math.sin(x / 5);
      const ny = 0.35 * Math.cos(y / 6);
      const nz = Math.sqrt(1 - nx * nx - ny * ny);
      return [Math.round(127.5 + 127.5 * nx), Math.round(127.5 + 127.5 * ny), Math.round(127.5 + 127.5 * nz), 255];
    },
    false,
  );
}
