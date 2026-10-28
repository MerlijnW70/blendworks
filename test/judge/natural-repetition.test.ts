import { describe, expect, it } from "vitest";
import { circularAutocorrelation, fft } from "../../src/judge/fft.js";
import { autocorrelationPeak, highPass, luminance, repetitionOf, REPETITION_MIN_SHIFT, type Grey } from "../../src/judge/natural-repetition.js";
import type { Pixels } from "../../src/judge/visual/png.js";

const SIZE = 512;

function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return (state + 0.5) / 2 ** 32;
  };
}

function noise(size: number, seed: number): Float64Array {
  const next = random(seed);
  let values = Float64Array.from({ length: size * size }, () => next());
  for (let pass = 0; pass < 2; pass += 1) {
    const before = values;
    values = new Float64Array(before.length);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        let sum = 0;
        for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) sum += before[((y + dy + size) % size) * size + ((x + dx + size) % size)]!;
        values[y * size + x] = sum / 9;
      }
    }
  }
  return values;
}

function tiled(tile: Float64Array, tileSize: number, repeats: number): Grey {
  const size = tileSize * repeats;
  const values = new Float64Array(size * size);
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) values[y * size + x] = tile[(y % tileSize) * tileSize + (x % tileSize)]!;
  return { width: size, height: size, values };
}

function splat(points: [number, number][], radius: number): Grey {
  const values = new Float64Array(SIZE * SIZE);
  for (const [px, py] of points) {
    for (let y = Math.floor(py - radius); y <= py + radius; y += 1) {
      for (let x = Math.floor(px - radius); x <= px + radius; x += 1) {
        if (x >= 0 && y >= 0 && x < SIZE && y < SIZE && (x - px) ** 2 + (y - py) ** 2 <= radius * radius) values[y * SIZE + x] = 1;
      }
    }
  }
  return { width: SIZE, height: SIZE, values };
}

function poissonDisk(spacing: number, seed: number): [number, number][] {
  const next = random(seed);
  const points: [number, number][] = [];
  for (let attempt = 0; attempt < 40_000; attempt += 1) {
    const point: [number, number] = [next() * SIZE, next() * SIZE];
    if (points.every(([x, y]) => (x - point[0]) ** 2 + (y - point[1]) ** 2 >= spacing * spacing)) points.push(point);
  }
  return points;
}

function jitteredGrid(cells: number, jitter: number, seed: number): [number, number][] {
  const next = random(seed);
  const step = SIZE / cells;
  const points: [number, number][] = [];
  for (let row = 0; row < cells; row += 1) for (let column = 0; column < cells; column += 1) points.push([(column + 0.5 + jitter * (2 * next() - 1)) * step, (row + 0.5 + jitter * (2 * next() - 1)) * step]);
  return points;
}

function peak(grey: Grey) {
  return autocorrelationPeak(highPass(grey));
}

describe("the FFT behind the repetition measure", () => {
  it("transforms an impulse to a flat spectrum and back", () => {
    const real = new Float64Array(8);
    const imaginary = new Float64Array(8);
    real[0] = 1;
    fft(real, imaginary);
    expect([...real]).toEqual(Array(8).fill(1));
    fft(real, imaginary, true);
    expect(real[0]).toBeCloseTo(1, 12);
    expect(real[3]).toBeCloseTo(0, 12);
  });

  it("gives the autocorrelation a direct sum gives", () => {
    const values = Float64Array.from({ length: 16 }, (_, index) => (index * 7) % 5);
    const products = circularAutocorrelation(values, 4, 4);
    let direct = 0;
    for (let y = 0; y < 4; y += 1) for (let x = 0; x < 4; x += 1) direct += values[y * 4 + x]! * values[((y + 1) % 4) * 4 + ((x + 2) % 4)]!;
    expect(products[1 * 4 + 2]).toBeCloseTo(direct, 9);
  });
});

describe("natural.repetition: the highest normalised autocorrelation away from zero shift", () => {
  it("gives 1.0 within rounding for an exactly tiled texture, at the tile's period", () => {
    const four = peak(tiled(noise(128, 1), 128, 4));
    expect(four.peak).toBe(1);
    expect(Math.hypot(...four.shift!)).toBe(128);
    const two = peak(tiled(noise(256, 2), 256, 2));
    expect(two.peak).toBe(1);
    expect(Math.hypot(...two.shift!)).toBe(256);
  });

  it("stays low for an untiled texture of the same noise", () => {
    expect(peak(tiled(noise(SIZE, 3), SIZE, 1)).peak).toBeLessThan(0.2);
  });

  it("keeps a Poisson-disk splat under 0.2", () => {
    expect(peak(splat(poissonDisk(0.06 * SIZE, 5), 6)).peak).toBeLessThan(0.2);
  });

  it("puts a jittered grid between the Poisson disk and an exact grid", () => {
    const poisson = peak(splat(poissonDisk(0.06 * SIZE, 5), 8)).peak!;
    const jittered = peak(splat(jitteredGrid(12, 0.2, 9), 8)).peak!;
    const exact = peak(splat(jitteredGrid(12, 0, 9), 8)).peak!;
    expect(jittered).toBeGreaterThan(poisson + 0.1);
    expect(jittered).toBeLessThan(exact - 0.3);
    expect(exact).toBe(1);
  });

  it("ignores shifts within 16 px of zero and shifts with less than a quarter overlap", () => {
    const stripes: Grey = { width: SIZE, height: SIZE, values: Float64Array.from({ length: SIZE * SIZE }, (_, index) => ((index % SIZE) % 12 < 6 ? 1 : 0)) };
    const found = peak(stripes);
    expect(found.peak).toBe(1);
    expect(Math.hypot(...found.shift!)).toBeGreaterThan(REPETITION_MIN_SHIFT);
    const lone: Grey = { width: SIZE, height: SIZE, values: new Float64Array(SIZE * SIZE) };
    for (let y = 40; y < 80; y += 1) for (let x = 40; x < 80; x += 1) lone.values[y * SIZE + x] = (x + y) % 2;
    for (let y = 40; y < 80; y += 1) for (let x = 440; x < 480; x += 1) lone.values[y * SIZE + x] = (x + y) % 2;
    expect(peak(lone).peak ?? 0).toBeLessThan(0.5);
  });

  it("removes smooth shading, so a lit gradient alone shows no repetition", () => {
    const ramp: Grey = { width: SIZE, height: SIZE, values: Float64Array.from({ length: SIZE * SIZE }, (_, index) => (index % SIZE) / SIZE + Math.floor(index / SIZE) / SIZE) };
    expect(peak(ramp).peak).toBeNull();
  });

  it("reads luminance from the stored RGB of a view", () => {
    const image: Pixels = { width: 2, height: 1, rgba: Uint8Array.from([255, 255, 255, 255, 255, 0, 0, 255]) };
    const grey = luminance(image);
    expect(grey.values[0]).toBeCloseTo(1, 9);
    expect(grey.values[1]).toBeCloseTo(0.2126, 9);
    expect(repetitionOf(image).peak).toBeNull();
  });
});
