import type { Pixels } from "./visual/png.js";

export type Mask = { width: number; height: number; inside: Uint8Array };

export type MaskChannel = "alpha" | "luminance";

export type MaskComparison = {
  assetPixels: number;
  referencePixels: number;
  intersection: number;
  union: number;
  iou: number;
  edges: { asset: number; reference: number };
  boundaryPixels: number | null;
  boundaryDistance: number | null;
};

const ALPHA_INSIDE = 128;
const LUMINANCE_INSIDE = 127.5;
const FAR = 1e20;
const DIGITS = 1e6;

function rounded(value: number): number {
  return Math.round(value * DIGITS) / DIGITS;
}

export function maskChannel(pixels: Pixels): MaskChannel {
  for (let index = 3; index < pixels.rgba.length; index += 4) if (pixels.rgba[index] !== 255) return "alpha";
  return "luminance";
}

export function maskFromPixels(pixels: Pixels, channel: MaskChannel = maskChannel(pixels)): Mask {
  const { width, height, rgba } = pixels;
  const inside = new Uint8Array(width * height);
  for (let index = 0; index < inside.length; index += 1) {
    const at = index * 4;
    const value = channel === "alpha" ? rgba[at + 3]! >= ALPHA_INSIDE : 0.2126 * rgba[at]! + 0.7152 * rgba[at + 1]! + 0.0722 * rgba[at + 2]! >= LUMINANCE_INSIDE;
    inside[index] = value ? 1 : 0;
  }
  return { width, height, inside };
}

export function maskFrom(width: number, height: number, test: (x: number, y: number) => boolean): Mask {
  const inside = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) inside[y * width + x] = test(x, y) ? 1 : 0;
  return { width, height, inside };
}

export function edgesOf(mask: Mask): Uint8Array {
  const { width, height, inside } = mask;
  const edges = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const at = y * width + x;
      if (inside[at] === 0) continue;
      const outside = (x > 0 && inside[at - 1] === 0) || (x < width - 1 && inside[at + 1] === 0) || (y > 0 && inside[at - width] === 0) || (y < height - 1 && inside[at + width] === 0);
      edges[at] = outside ? 1 : 0;
    }
  }
  return edges;
}

function transformLine(values: Float64Array, length: number, out: Float64Array, hull: Int32Array, bounds: Float64Array): void {
  const crossing = (q: number, v: number) => (values[q]! + q * q - (values[v]! + v * v)) / (2 * q - 2 * v);
  let top = 0;
  hull[0] = 0;
  bounds[0] = -Infinity;
  bounds[1] = Infinity;
  for (let q = 1; q < length; q += 1) {
    let meet = crossing(q, hull[top]!);
    while (meet <= bounds[top]!) {
      top -= 1;
      meet = crossing(q, hull[top]!);
    }
    top += 1;
    hull[top] = q;
    bounds[top] = meet;
    bounds[top + 1] = Infinity;
  }
  let k = 0;
  for (let q = 0; q < length; q += 1) {
    while (bounds[k + 1]! < q) k += 1;
    const v = hull[k]!;
    out[q] = (q - v) * (q - v) + values[v]!;
  }
}

export function squaredDistances(edges: Uint8Array, width: number, height: number): Float64Array {
  const grid = new Float64Array(width * height);
  for (let index = 0; index < grid.length; index += 1) grid[index] = edges[index] === 1 ? 0 : FAR;
  const longest = Math.max(width, height);
  const line = new Float64Array(longest);
  const out = new Float64Array(longest);
  const hull = new Int32Array(longest);
  const bounds = new Float64Array(longest + 1);
  for (let x = 0; x < width; x += 1) {
    for (let y = 0; y < height; y += 1) line[y] = grid[y * width + x]!;
    transformLine(line, height, out, hull, bounds);
    for (let y = 0; y < height; y += 1) grid[y * width + x] = out[y]!;
  }
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) line[x] = grid[y * width + x]!;
    transformLine(line, width, out, hull, bounds);
    for (let x = 0; x < width; x += 1) grid[y * width + x] = out[x]!;
  }
  return grid;
}

function distanceSum(from: Uint8Array, to: Float64Array): number {
  let sum = 0;
  for (let index = 0; index < from.length; index += 1) if (from[index] === 1) sum += Math.sqrt(to[index]!);
  return sum;
}

function counted(values: Uint8Array): number {
  let total = 0;
  for (const value of values) total += value;
  return total;
}

export function compareMasks(asset: Mask, reference: Mask): MaskComparison {
  if (asset.width !== reference.width || asset.height !== reference.height) throw new Error("masks of different sizes cannot be compared");
  let intersection = 0;
  let union = 0;
  for (let index = 0; index < asset.inside.length; index += 1) {
    const a = asset.inside[index]!;
    const b = reference.inside[index]!;
    intersection += a & b;
    union += a | b;
  }
  const assetEdges = edgesOf(asset);
  const referenceEdges = edgesOf(reference);
  const edges = { asset: counted(assetEdges), reference: counted(referenceEdges) };
  let boundaryPixels: number | null = null;
  if (edges.asset === 0 && edges.reference === 0) boundaryPixels = 0;
  else if (edges.asset > 0 && edges.reference > 0) {
    const toReference = squaredDistances(referenceEdges, reference.width, reference.height);
    const toAsset = squaredDistances(assetEdges, asset.width, asset.height);
    boundaryPixels = (distanceSum(assetEdges, toReference) + distanceSum(referenceEdges, toAsset)) / (edges.asset + edges.reference);
  }
  return {
    assetPixels: counted(asset.inside),
    referencePixels: counted(reference.inside),
    intersection,
    union,
    iou: union === 0 ? 1 : rounded(intersection / union),
    edges,
    boundaryPixels: boundaryPixels === null ? null : rounded(boundaryPixels),
    boundaryDistance: boundaryPixels === null ? null : rounded(boundaryPixels / asset.width),
  };
}

const BOTH = [235, 235, 235];
const ASSET_ONLY = [230, 80, 60];
const REFERENCE_ONLY = [60, 130, 240];
const NEITHER = [24, 24, 24];

export function overlayImage(asset: Mask, reference: Mask): Pixels {
  const rgba = new Uint8Array(asset.width * asset.height * 4);
  for (let index = 0; index < asset.inside.length; index += 1) {
    const a = asset.inside[index] === 1;
    const b = reference.inside[index] === 1;
    rgba.set([...(a && b ? BOTH : a ? ASSET_ONLY : b ? REFERENCE_ONLY : NEITHER), 255], index * 4);
  }
  return { width: asset.width, height: asset.height, rgba };
}

export function maskImage(mask: Mask): Pixels {
  const rgba = new Uint8Array(mask.width * mask.height * 4);
  for (let index = 0; index < mask.inside.length; index += 1) {
    const value = mask.inside[index] === 1 ? 255 : 0;
    rgba.set([value, value, value, 255], index * 4);
  }
  return { width: mask.width, height: mask.height, rgba };
}
