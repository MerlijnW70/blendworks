import { describe, expect, it } from "vitest";
import { boxCountingDimension, convexHull, polygonArea, solidity } from "../../src/judge/natural-measures.js";
import { maskFrom, type Mask } from "../../src/judge/silhouette.js";

type Point = [number, number];

function polygonMask(size: number, polygon: Point[]): Mask {
  const inside = new Uint8Array(size * size);
  for (let y = 0; y < size; y += 1) {
    const row = y + 0.5;
    const crossings: number[] = [];
    for (let index = 0; index < polygon.length; index += 1) {
      const [x0, y0] = polygon[index]!;
      const [x1, y1] = polygon[(index + 1) % polygon.length]!;
      if (y0 <= row !== y1 <= row) crossings.push(x0 + ((row - y0) / (y1 - y0)) * (x1 - x0));
    }
    crossings.sort((a, b) => a - b);
    for (let pair = 0; pair + 1 < crossings.length; pair += 2) {
      for (let x = Math.max(0, Math.ceil(crossings[pair]! - 0.5)); x <= Math.min(size - 1, Math.floor(crossings[pair + 1]! - 0.5)); x += 1) inside[y * size + x] = 1;
    }
  }
  return { width: size, height: size, inside };
}

function koch(depth: number, size: number): Point[] {
  const radius = size * 0.42;
  const centre = size / 2;
  let points: Point[] = [0, 1, 2].map((corner) => {
    const angle = -Math.PI / 2 + (corner * 2 * Math.PI) / 3;
    return [centre + radius * Math.cos(angle), centre + radius * Math.sin(angle)];
  });
  for (let level = 0; level < depth; level += 1) {
    const next: Point[] = [];
    for (let index = 0; index < points.length; index += 1) {
      const [ax, ay] = points[index]!;
      const [bx, by] = points[(index + 1) % points.length]!;
      const dx = (bx - ax) / 3;
      const dy = (by - ay) / 3;
      const first: Point = [ax + dx, ay + dy];
      const second: Point = [ax + 2 * dx, ay + 2 * dy];
      const peak: Point = [first[0] + dx * Math.cos(-Math.PI / 3) - dy * Math.sin(-Math.PI / 3), first[1] + dx * Math.sin(-Math.PI / 3) + dy * Math.cos(-Math.PI / 3)];
      next.push([ax, ay], first, peak, second);
    }
    points = next;
  }
  return points;
}

describe("box-counting dimension of a silhouette edge, boxes of 2 to 64 px", () => {
  it("gives 1.00 within 0.05 for a circle", () => {
    const circle = maskFrom(1024, 1024, (x, y) => (x + 0.5 - 512) ** 2 + (y + 0.5 - 512) ** 2 <= 420 ** 2);
    expect(boxCountingDimension(circle).dimension).toBeCloseTo(1.0, 1);
    expect(Math.abs(boxCountingDimension(circle).dimension! - 1)).toBeLessThanOrEqual(0.05);
  });

  it("gives log 4 / log 3 within 0.05 for a Koch snowflake of depth 7", () => {
    const measured = boxCountingDimension(polygonMask(1024, koch(7, 1024)));
    expect(Math.abs(measured.dimension! - Math.log(4) / Math.log(3))).toBeLessThanOrEqual(0.05);
  });

  it("tells a Koch snowflake from a circle and from a triangle", () => {
    const snowflake = boxCountingDimension(polygonMask(1024, koch(7, 1024))).dimension!;
    const triangle = boxCountingDimension(polygonMask(1024, koch(0, 1024))).dimension!;
    expect(snowflake - triangle).toBeGreaterThan(0.2);
  });

  it("reports no dimension for an empty silhouette", () => {
    expect(boxCountingDimension(maskFrom(64, 64, () => false)).dimension).toBeNull();
  });
});

describe("solidity: silhouette area over convex hull area", () => {
  it("gives 1 for a square", () => {
    const square = maskFrom(256, 256, (x, y) => x >= 40 && x < 200 && y >= 40 && y < 200);
    expect(solidity(square)).toEqual({ solidity: 1, area: 160 * 160, hullArea: 160 * 160 });
  });

  it("gives 7500 / 8750 for a 100 px L-shape missing a 50 px quadrant", () => {
    const shape = maskFrom(200, 200, (x, y) => x >= 20 && x < 120 && y >= 20 && y < 120 && !(x >= 70 && y >= 70));
    const measured = solidity(shape);
    expect(measured.area).toBe(100 * 100 - 50 * 50);
    expect(measured.hullArea).toBe(100 * 100 - (50 * 50) / 2);
    expect(measured.solidity).toBeCloseTo(7500 / 8750, 6);
  });

  it("counts a silhouette that touches the image border", () => {
    expect(solidity(maskFrom(32, 32, (x) => x < 16)).solidity).toBe(1);
  });

  it("reports no solidity for an empty silhouette", () => {
    expect(solidity(maskFrom(32, 32, () => false)).solidity).toBeNull();
  });

  it("finds the hull of collinear and repeated points", () => {
    const hull = convexHull([
      [0, 0],
      [2, 0],
      [1, 0],
      [2, 2],
      [0, 2],
      [1, 1],
      [0, 0],
    ]);
    expect(polygonArea(hull)).toBe(4);
    expect(hull).toHaveLength(4);
  });
});
