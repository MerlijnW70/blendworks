import { describe, expect, it } from "vitest";
import { compareMasks, edgesOf, maskChannel, maskFrom, maskFromPixels, overlayImage, squaredDistances } from "../../src/judge/silhouette.js";

function square(size: number, low: number, high: number) {
  return maskFrom(size, size, (x, y) => x >= low && x < high && y >= low && y < high);
}

function disk(size: number, centre: number, radius: number) {
  return maskFrom(size, size, (x, y) => (x + 0.5 - centre) ** 2 + (y + 0.5 - centre) ** 2 <= radius * radius);
}

function bruteForce(edges: Uint8Array, width: number, height: number): number[] {
  const points: [number, number][] = [];
  for (let index = 0; index < edges.length; index += 1) if (edges[index] === 1) points.push([index % width, Math.floor(index / width)]);
  return Array.from({ length: width * height }, (_, index) => Math.min(...points.map(([x, y]) => (x - (index % width)) ** 2 + (y - Math.floor(index / width)) ** 2)));
}

describe("silhouette comparison", () => {
  it("scores a silhouette against itself IoU 1 and boundary distance 0", () => {
    const shape = disk(64, 32, 20);
    expect(compareMasks(shape, shape)).toMatchObject({ iou: 1, boundaryDistance: 0, boundaryPixels: 0 });
  });

  it("scores half-planes 32 and 40 columns wide: IoU 32/40, edges 8 px apart, 8/64 of the view", () => {
    const left = maskFrom(64, 64, (x) => x < 32);
    const wider = maskFrom(64, 64, (x) => x < 40);
    expect(compareMasks(left, wider)).toEqual({
      assetPixels: 2048,
      referencePixels: 2560,
      intersection: 2048,
      union: 2560,
      iou: 0.8,
      edges: { asset: 64, reference: 64 },
      boundaryPixels: 8,
      boundaryDistance: 0.125,
    });
  });

  it("scores a 10 px square centred in a 20 px square: IoU 100/400, and the mean of both rings' distances", () => {
    const outer = square(40, 10, 30);
    const inner = square(40, 15, 25);
    const corners = [50, 41, 34, 29, 26].reduce((sum, value) => sum + Math.sqrt(value), 0);
    const outerSum = 4 * (10 * 5 + 2 * corners) - 4 * Math.sqrt(50);
    const innerSum = 36 * 5;
    const compared = compareMasks(outer, inner);
    expect(compared).toMatchObject({ iou: 0.25, intersection: 100, union: 400, edges: { asset: 76, reference: 36 } });
    expect(compared.boundaryPixels).toBeCloseTo((outerSum + innerSum) / 112, 6);
    expect(compared.boundaryDistance).toBeCloseTo((outerSum + innerSum) / 112 / 40, 6);
  });

  it("scores a 200 px square against its inscribed circle at IoU pi/4, the boundary between the two one-way means", () => {
    const compared = compareMasks(square(256, 28, 228), disk(256, 128, 100));
    expect(compared.intersection).toBe(compared.referencePixels);
    expect(compared.union).toBe(40000);
    expect(compared.iou).toBeCloseTo(Math.PI / 4, 3);
    const squareToCircle = 100 * (Math.SQRT2 / 2 + Math.asinh(1) / 2 - 1);
    const circleToSquare = 100 * (1 - (2 * Math.SQRT2) / Math.PI);
    expect(compared.boundaryPixels!).toBeGreaterThan(circleToSquare);
    expect(compared.boundaryPixels!).toBeLessThan(squareToCircle);
  });

  it("gives IoU 1 and distance 0 for two empty views, and no distance when only one is empty", () => {
    const empty = maskFrom(16, 16, () => false);
    expect(compareMasks(empty, empty)).toMatchObject({ iou: 1, union: 0, boundaryDistance: 0 });
    expect(compareMasks(empty, square(16, 4, 12))).toMatchObject({ iou: 0, intersection: 0, union: 64, boundaryDistance: null, boundaryPixels: null });
  });

  it("refuses to compare views of different sizes", () => {
    expect(() => compareMasks(square(16, 4, 12), square(32, 4, 12))).toThrow("different sizes");
  });

  it("counts as edge an inside pixel beside an outside pixel, but not the frame of the image", () => {
    const full = maskFrom(8, 8, () => true);
    expect(edgesOf(full).reduce((sum, value) => sum + value, 0)).toBe(0);
    expect(Array.from(edgesOf(square(6, 1, 5)))).toEqual(Array.from(maskFrom(6, 6, (x, y) => (x === 1 || x === 4 || y === 1 || y === 4) && x >= 1 && x <= 4 && y >= 1 && y <= 4).inside));
  });

  it("finds the exact Euclidean distance to the nearest edge, as a brute force search does", () => {
    let seed = 7;
    const random = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed / 2147483648;
    };
    for (let round = 0; round < 5; round += 1) {
      const width = 17 + round;
      const height = 23 - round;
      const edges = Uint8Array.from({ length: width * height }, () => (random() < 0.04 ? 1 : 0));
      edges[round] = 1;
      expect(Array.from(squaredDistances(edges, width, height))).toEqual(bruteForce(edges, width, height));
    }
  });
});

describe("masks from PNG pixels", () => {
  const pixels = (values: number[][]) => ({ width: values.length, height: 1, rgba: Uint8Array.from(values.flat()) });

  it("reads an opaque image by luminance, inside from 0.5 up", () => {
    const image = pixels([
      [128, 128, 128, 255],
      [127, 127, 127, 255],
      [255, 0, 0, 255],
      [0, 255, 0, 255],
    ]);
    expect(maskChannel(image)).toBe("luminance");
    expect(Array.from(maskFromPixels(image).inside)).toEqual([1, 0, 0, 1]);
  });

  it("reads an image with transparency by alpha, inside from 128 up", () => {
    const image = pixels([
      [0, 0, 0, 128],
      [255, 255, 255, 127],
      [0, 0, 0, 255],
    ]);
    expect(maskChannel(image)).toBe("alpha");
    expect(Array.from(maskFromPixels(image).inside)).toEqual([1, 0, 1]);
  });

  it("draws both silhouettes in an overlay: white for both, red for the asset only, blue for the reference only", () => {
    const asset = maskFrom(4, 1, (x) => x < 2);
    const reference = maskFrom(4, 1, (x) => x === 1 || x === 2);
    expect(Array.from(overlayImage(asset, reference).rgba)).toEqual([230, 80, 60, 255, 235, 235, 235, 255, 60, 130, 240, 255, 24, 24, 24, 255]);
  });
});
