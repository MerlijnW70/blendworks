export const DELTA_CEILING = 10;

const BISECTIONS = 100;
const DIGITS = 1e4;

export type DeltaSolution = { delta: number; above: boolean } | null;

function rounded(value: number): number {
  return Math.round(value * DIGITS) / DIGITS;
}

function surplus(ratios: readonly number[], delta: number): number {
  return ratios.reduce((sum, ratio) => sum + ratio ** delta, 0) - 1;
}

export function solveDelta(parent: number, children: readonly number[]): DeltaSolution {
  if (!(parent > 0) || children.length < 2 || children.some((child) => !(child > 0))) return null;
  const ratios = children.map((child) => child / parent);
  if (ratios.some((ratio) => ratio >= 1) || surplus(ratios, DELTA_CEILING) > 0) return { delta: DELTA_CEILING, above: true };
  let low = 0;
  let high = DELTA_CEILING;
  for (let step = 0; step < BISECTIONS; step += 1) {
    const middle = (low + high) / 2;
    if (surplus(ratios, middle) > 0) low = middle;
    else high = middle;
  }
  return { delta: (low + high) / 2, above: false };
}

export function quantile(sorted: readonly number[], share: number): number {
  const position = (sorted.length - 1) * share;
  const low = Math.floor(position);
  const high = Math.ceil(position);
  return sorted[low]! + (sorted[high]! - sorted[low]!) * (position - low);
}

export type DeltaSummary = { median: number | null; p25: number | null; p75: number | null; solved: number; above: number; invalid: number; deltas: number[] };

export function summarizeDeltas(branchings: readonly (readonly number[])[]): DeltaSummary {
  const values: number[] = [];
  let above = 0;
  let invalid = 0;
  for (const radii of branchings) {
    const solution = solveDelta(radii[0] ?? 0, radii.slice(1));
    if (solution === null) {
      invalid += 1;
      continue;
    }
    if (solution.above) above += 1;
    values.push(solution.delta);
  }
  const sorted = [...values].sort((a, b) => a - b);
  const at = (share: number) => (sorted.length === 0 ? null : rounded(quantile(sorted, share)));
  return { median: at(0.5), p25: at(0.25), p75: at(0.75), solved: values.length - above, above, invalid, deltas: values.map(rounded) };
}
