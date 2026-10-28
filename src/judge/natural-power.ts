export const MIN_TAIL = 50;
export const MAX_CANDIDATES = 400;
export const EXPONENT_RANGE = [-12, 8] as const;

const BISECTIONS = 100;
const FLAT = 1e-9;
const DIGITS = 1e4;

export type PowerFit = { exponent: number | null; xMin: number | null; xMax: number | null; tail: number; ks: number | null; failure: string | null };

function rounded(value: number): number {
  return Math.round(value * DIGITS) / DIGITS;
}

export function expectedLog(exponent: number, low: number, high: number): number {
  const shift = exponent + 1;
  const logLow = Math.log(low);
  const logHigh = Math.log(high);
  if (Math.abs(shift) < FLAT) return (logLow + logHigh) / 2;
  if (shift > 0) {
    const ratio = Math.exp(shift * (logLow - logHigh));
    return (logHigh - ratio * logLow) / (1 - ratio) - 1 / shift;
  }
  const ratio = Math.exp(shift * (logHigh - logLow));
  return (ratio * logHigh - logLow) / (ratio - 1) - 1 / shift;
}

export function powerCdf(value: number, exponent: number, low: number, high: number): number {
  const shift = exponent + 1;
  if (Math.abs(shift) < FLAT) return Math.log(value / low) / Math.log(high / low);
  if (shift > 0) {
    const bottom = Math.exp(shift * Math.log(low / high));
    return (Math.exp(shift * Math.log(value / high)) - bottom) / (1 - bottom);
  }
  const top = Math.exp(shift * Math.log(high / low));
  return (Math.exp(shift * Math.log(value / low)) - 1) / (top - 1);
}

export function fitExponent(tail: readonly number[], low: number, high: number): number {
  const meanLog = tail.reduce((sum, value) => sum + Math.log(value), 0) / tail.length;
  let left: number = EXPONENT_RANGE[0];
  let right: number = EXPONENT_RANGE[1];
  for (let step = 0; step < BISECTIONS; step += 1) {
    const middle = (left + right) / 2;
    if (expectedLog(middle, low, high) < meanLog) left = middle;
    else right = middle;
  }
  return (left + right) / 2;
}

export function ksDistance(tail: readonly number[], exponent: number, low: number, high: number): number {
  let distance = 0;
  const count = tail.length;
  for (let index = 0; index < count; index += 1) {
    const model = powerCdf(tail[index]!, exponent, low, high);
    distance = Math.max(distance, Math.abs(model - index / count), Math.abs(model - (index + 1) / count));
  }
  return distance;
}

function candidates(sorted: readonly number[], minTail: number): number[] {
  const starts: number[] = [];
  for (let index = 0; index <= sorted.length - minTail; index += 1) {
    if (index === 0 || sorted[index]! > sorted[index - 1]!) starts.push(index);
  }
  if (starts.length <= MAX_CANDIDATES) return starts;
  return [...new Set(Array.from({ length: MAX_CANDIDATES }, (_, at) => starts[Math.round((at * (starts.length - 1)) / (MAX_CANDIDATES - 1))]!))];
}

export function fitPowerLaw(sizes: readonly number[], minTail = MIN_TAIL): PowerFit {
  const sorted = sizes.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
  const empty = { exponent: null, xMin: null, xMax: null, ks: null };
  if (sorted.length < minTail) return { ...empty, tail: sorted.length, failure: `${sorted.length} sizes, fewer than the ${minTail} a fit needs` };
  const high = sorted[sorted.length - 1]!;
  let best: { exponent: number; start: number; ks: number } | null = null;
  for (const start of candidates(sorted, minTail)) {
    const low = sorted[start]!;
    if (high <= low * (1 + FLAT)) continue;
    const tail = sorted.slice(start);
    const exponent = fitExponent(tail, low, high);
    const ks = ksDistance(tail, exponent, low, high);
    if (best === null || ks < best.ks) best = { exponent, start, ks };
  }
  if (best === null) return { ...empty, tail: sorted.length, failure: "the sizes are all the same, so no power law fits" };
  return { exponent: rounded(best.exponent), xMin: sorted[best.start]!, xMax: high, tail: sorted.length - best.start, ks: rounded(best.ks), failure: null };
}
