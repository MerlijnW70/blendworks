import type { Mask } from "./silhouette.js";

export const BOX_SIZES = [2, 4, 8, 16, 32, 64] as const;

const DIGITS = 1e6;

function rounded(value: number): number {
  return Math.round(value * DIGITS) / DIGITS;
}

export const OFFSET_STEPS = 8;

export function curveEdges(mask: Mask): Uint8Array {
  const { width, height, inside } = mask;
  const edges = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (inside[y * width + x] === 0) continue;
      let outside = false;
      for (let dy = -1; dy <= 1 && !outside; dy += 1) {
        for (let dx = -1; dx <= 1 && !outside; dx += 1) {
          const nx = x + dx;
          const ny = y + dy;
          outside = nx < 0 || ny < 0 || nx >= width || ny >= height || inside[ny * width + nx] === 0;
        }
      }
      edges[y * width + x] = outside ? 1 : 0;
    }
  }
  return edges;
}

export function edgePoints(edges: Uint8Array, width: number): Int32Array {
  let total = 0;
  for (const value of edges) total += value;
  const points = new Int32Array(total * 2);
  let at = 0;
  for (let index = 0; index < edges.length; index += 1) {
    if (edges[index] === 0) continue;
    points[at] = index % width;
    points[at + 1] = Math.floor(index / width);
    at += 2;
  }
  return points;
}

export function occupiedBoxes(points: Int32Array, width: number, height: number, box: number, offsetX = 0, offsetY = 0): number {
  const columns = Math.ceil((width + offsetX) / box);
  const occupied = new Uint8Array(columns * Math.ceil((height + offsetY) / box));
  let count = 0;
  for (let at = 0; at < points.length; at += 2) {
    const cell = Math.floor((points[at + 1]! + offsetY) / box) * columns + Math.floor((points[at]! + offsetX) / box);
    if (occupied[cell] === 0) {
      occupied[cell] = 1;
      count += 1;
    }
  }
  return count;
}

export function meanOccupiedBoxes(points: Int32Array, width: number, height: number, box: number): number {
  const step = Math.max(1, box / OFFSET_STEPS);
  let total = 0;
  let grids = 0;
  for (let offsetY = 0; offsetY < box; offsetY += step) {
    for (let offsetX = 0; offsetX < box; offsetX += step) {
      total += occupiedBoxes(points, width, height, box, offsetX, offsetY);
      grids += 1;
    }
  }
  return total / grids;
}

export function fittedSlope(xs: readonly number[], ys: readonly number[]): number {
  const n = xs.length;
  const meanX = xs.reduce((sum, value) => sum + value, 0) / n;
  const meanY = ys.reduce((sum, value) => sum + value, 0) / n;
  let covariance = 0;
  let variance = 0;
  for (let index = 0; index < n; index += 1) {
    covariance += (xs[index]! - meanX) * (ys[index]! - meanY);
    variance += (xs[index]! - meanX) ** 2;
  }
  return covariance / variance;
}

export type BoxCount = { dimension: number | null; edgePixels: number; counts: number[] };

export function boxCountingDimension(mask: Mask): BoxCount {
  const points = edgePoints(curveEdges(mask), mask.width);
  const edgePixels = points.length / 2;
  const counts = BOX_SIZES.map((box) => rounded(meanOccupiedBoxes(points, mask.width, mask.height, box)));
  if (edgePixels === 0) return { dimension: null, edgePixels, counts };
  const slope = fittedSlope(
    BOX_SIZES.map((box) => Math.log(box)),
    counts.map((count) => Math.log(count)),
  );
  return { dimension: rounded(-slope), edgePixels, counts };
}

type Point = readonly [number, number];

function cross(origin: Point, first: Point, second: Point): number {
  return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0]);
}

export function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length < 3) return sorted;
  const build = (ordered: Point[]): Point[] => {
    const chain: Point[] = [];
    for (const point of ordered) {
      while (chain.length >= 2 && cross(chain[chain.length - 2]!, chain[chain.length - 1]!, point) <= 0) chain.pop();
      chain.push(point);
    }
    chain.pop();
    return chain;
  };
  return [...build(sorted), ...build([...sorted].reverse())];
}

export function polygonArea(points: Point[]): number {
  let doubled = 0;
  for (let index = 0; index < points.length; index += 1) {
    const [x0, y0] = points[index]!;
    const [x1, y1] = points[(index + 1) % points.length]!;
    doubled += x0 * y1 - x1 * y0;
  }
  return Math.abs(doubled) / 2;
}

function onBoundary(mask: Mask, x: number, y: number): boolean {
  const { width, height, inside } = mask;
  const at = y * width + x;
  if (inside[at] === 0) return false;
  return x === 0 || y === 0 || x === width - 1 || y === height - 1 || inside[at - 1] === 0 || inside[at + 1] === 0 || inside[at - width] === 0 || inside[at + width] === 0;
}

function boundaryCorners(mask: Mask): Point[] {
  const seen = new Set<number>();
  const corners: Point[] = [];
  const stride = mask.width + 1;
  for (let y = 0; y < mask.height; y += 1) {
    for (let x = 0; x < mask.width; x += 1) {
      if (!onBoundary(mask, x, y)) continue;
      for (const [cx, cy] of [
        [x, y],
        [x + 1, y],
        [x, y + 1],
        [x + 1, y + 1],
      ] as const) {
        const key = cy * stride + cx;
        if (seen.has(key)) continue;
        seen.add(key);
        corners.push([cx, cy]);
      }
    }
  }
  return corners;
}

export type Solidity = { solidity: number | null; area: number; hullArea: number };

export function solidity(mask: Mask): Solidity {
  let area = 0;
  for (const value of mask.inside) area += value;
  if (area === 0) return { solidity: null, area, hullArea: 0 };
  const hullArea = polygonArea(convexHull(boundaryCorners(mask)));
  return { solidity: hullArea === 0 ? null : rounded(area / hullArea), area, hullArea };
}
