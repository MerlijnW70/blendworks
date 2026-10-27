import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { cacheRoot, repoRoot } from "./paths.js";
import type { Timing } from "./timings.js";

export const BASELINE_DURATIONS = join(repoRoot, "scripts", "durations.json");

export type Durations = Record<string, number>;

const SCHEDULED = /^(test\/.+\.test\.ts|bridge\/tests\/test_\w+\.py)$/;

export function measuredDurationsPath(root: string = cacheRoot()): string {
  return join(root, "timings", "durations.json");
}

function readDurations(path: string): Durations {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
    if (parsed === null || typeof parsed !== "object") return {};
    return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])));
  } catch {
    return {};
  }
}

export function knownDurations(root: string = cacheRoot()): Durations {
  return { ...readDurations(BASELINE_DURATIONS), ...readDurations(measuredDurationsPath(root)) };
}

export function rememberDurations(timings: Timing[], root: string = cacheRoot()): Durations {
  const path = measuredDurationsPath(root);
  const merged = readDurations(path);
  for (const timing of timings) if (timing.kind === "file" && SCHEDULED.test(timing.file)) merged[timing.file] = Math.round((timing.wallMs - timing.waitMs) / 100) / 10;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(merged, Object.keys(merged).sort(), 2)}\n`);
  return merged;
}

export function heaviestFirst<T>(items: T[], key: (item: T) => string, durations: Durations, fallback: (item: T) => number = () => 0): T[] {
  return [...items].sort((a, b) => (durations[key(b)] ?? fallback(b)) - (durations[key(a)] ?? fallback(a)) || key(a).localeCompare(key(b)));
}

export function saveBaseline(root: string = cacheRoot()): number {
  const measured = readDurations(measuredDurationsPath(root));
  const names = Object.keys(measured);
  if (names.length === 0) return 0;
  const merged = { ...readDurations(BASELINE_DURATIONS), ...measured };
  writeFileSync(BASELINE_DURATIONS, `${JSON.stringify(merged, Object.keys(merged).sort(), 2)}\n`);
  return names.length;
}

export function durationsMain(): number {
  const saved = saveBaseline();
  if (saved === 0) {
    console.error("no measured durations yet: run npm run check first");
    return 1;
  }
  console.log(`saved ${saved} measured durations to scripts/durations.json`);
  return 0;
}
