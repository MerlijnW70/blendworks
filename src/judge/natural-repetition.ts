import { circularAutocorrelation, nextPowerOfTwo } from "./fft.js";
import type { Pixels } from "./visual/png.js";

export const REPETITION_MIN_SHIFT = 16;
export const REPETITION_MIN_OVERLAP = 0.25;
export const REPETITION_WINDOW = 2 * REPETITION_MIN_SHIFT + 1;

const DIGITS = 1e4;
export const REPETITION_MIN_ENERGY = 0.1;
const TIE = 1e-9;

export type Grey = { width: number; height: number; values: Float64Array };

export type RepetitionPeak = { peak: number | null; shift: [number, number] | null; size: [number, number] };

export function luminance(image: Pixels): Grey {
  const values = new Float64Array(image.width * image.height);
  for (let index = 0; index < values.length; index += 1) {
    const at = index * 4;
    values[index] = (0.2126 * image.rgba[at]! + 0.7152 * image.rgba[at + 1]! + 0.0722 * image.rgba[at + 2]!) / 255;
  }
  return { width: image.width, height: image.height, values };
}

function summedArea(values: Float64Array, width: number, height: number, squared = false): Float64Array {
  const stride = width + 1;
  const table = new Float64Array(stride * (height + 1));
  for (let y = 0; y < height; y += 1) {
    let row = 0;
    for (let x = 0; x < width; x += 1) {
      const value = values[y * width + x]!;
      row += squared ? value * value : value;
      table[(y + 1) * stride + x + 1] = table[y * stride + x + 1]! + row;
    }
  }
  return table;
}

function boxSum(table: Float64Array, stride: number, x0: number, y0: number, x1: number, y1: number): number {
  return table[y1 * stride + x1]! - table[y0 * stride + x1]! - table[y1 * stride + x0]! + table[y0 * stride + x0]!;
}

export function highPass(grey: Grey, window = REPETITION_WINDOW): Grey {
  const radius = (window - 1) / 2;
  const width = grey.width - 2 * radius;
  const height = grey.height - 2 * radius;
  if (width <= 0 || height <= 0) return { width: 0, height: 0, values: new Float64Array(0) };
  const table = summedArea(grey.values, grey.width, grey.height);
  const stride = grey.width + 1;
  const area = window * window;
  const values = new Float64Array(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const mean = boxSum(table, stride, x, y, x + window, y + window) / area;
      values[y * width + x] = grey.values[(y + radius) * grey.width + x + radius]! - mean;
    }
  }
  return { width, height, values };
}

function padded(grey: Grey, width: number, height: number): Float64Array {
  const values = new Float64Array(width * height);
  for (let y = 0; y < grey.height; y += 1) values.set(grey.values.subarray(y * grey.width, (y + 1) * grey.width), y * width);
  return values;
}

export function autocorrelationPeak(grey: Grey, minShift = REPETITION_MIN_SHIFT, minOverlap = REPETITION_MIN_OVERLAP): RepetitionPeak {
  const { width, height } = grey;
  const size: [number, number] = [width, height];
  if (width === 0 || height === 0) return { peak: null, shift: null, size };
  const fftWidth = nextPowerOfTwo(2 * width);
  const fftHeight = nextPowerOfTwo(2 * height);
  const products = circularAutocorrelation(padded(grey, fftWidth, fftHeight), fftWidth, fftHeight);
  const energy = summedArea(grey.values, width, height, true);
  const stride = width + 1;
  const total = boxSum(energy, stride, 0, 0, width, height);
  if (total <= 0) return { peak: null, shift: null, size };
  const quiet = REPETITION_MIN_ENERGY * total;
  const smallest = minOverlap * width * height;
  let peak = -Infinity;
  let shift: [number, number] | null = null;
  for (let dy = 0; dy < height; dy += 1) {
    for (let dx = -(width - 1); dx < width; dx += 1) {
      if (dy === 0 && dx <= 0) continue;
      if (dx * dx + dy * dy <= minShift * minShift) continue;
      const across = width - Math.abs(dx);
      const down = height - dy;
      if (across * down < smallest) continue;
      const firstX = dx >= 0 ? 0 : -dx;
      const secondX = dx >= 0 ? dx : 0;
      const first = boxSum(energy, stride, firstX, 0, firstX + across, down);
      const second = boxSum(energy, stride, secondX, dy, secondX + across, dy + down);
      if (first < quiet || second < quiet) continue;
      const product = products[dy * fftWidth + ((dx + fftWidth) % fftWidth)]!;
      const value = product / Math.sqrt(first * second);
      if (value > peak + TIE || (value >= peak - TIE && shift !== null && dx * dx + dy * dy < shift[0] ** 2 + shift[1] ** 2)) {
        peak = value;
        shift = [dx, dy];
      }
    }
  }
  if (shift === null) return { peak: null, shift: null, size };
  return { peak: Math.round(Math.min(1, peak) * DIGITS) / DIGITS, shift, size };
}

export function repetitionOf(image: Pixels): RepetitionPeak {
  return autocorrelationPeak(highPass(luminance(image)));
}
