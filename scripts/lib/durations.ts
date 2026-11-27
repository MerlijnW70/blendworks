import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { cacheRoot, repoRoot } from "./paths.js";
import type { Timing } from "./timings.js";

export const BASELINE_DURATIONS = join(repoRoot, "scripts", "durations.json");

export type Durations = Record<string, number>;

export const UNMEASURED_SECONDS = 1;

export const SCHEDULED_FILE = /^(test\/.+\.test\.ts|bridge\/tests\/test_\w+\.py)$/;

function testFilesIn(directory: string, prefix: string, pattern: RegExp): string[] {
  const folder = join(repoRoot, directory);
  if (!existsSync(folder)) return [];
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : testFilesIn(`${directory}/${entry.name}`, `${prefix}${entry.name}/`, pattern);
    return pattern.test(entry.name) ? [`${prefix}${entry.name}`] : [];
  });
}

export function ownStage(file: string): string | undefined {
  if (/^test\/.+\.test\.ts$/.test(file)) return "test";
  if (/^bridge\/tests\/test_\w+\.py$/.test(file)) return "test:bridge";
  return undefined;
}

export function topLevelRun(file: string, stage: string | undefined): boolean {
  return stage !== undefined && ownStage(file) === stage;
}

export function scheduledFiles(): string[] {
  return [...testFilesIn("test", "test/", /\.test\.ts$/), ...testFilesIn("bridge/tests", "bridge/tests/", /^test_\w+\.py$/)].sort();
}

export function missingDurations(files: string[], durations: Durations): string[] {
  return files.filter((file) => durations[file] === undefined);
}

export function baselineDurations(): Durations {
  return readDurations(BASELINE_DURATIONS);
}

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
  for (const timing of timings) if (timing.kind === "file" && topLevelRun(timing.file, timing.stage)) merged[timing.file] = Math.round((timing.wallMs - timing.waitMs) / 100) / 10;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(merged, Object.keys(merged).sort(), 2)}\n`);
  return merged;
}

export function heaviestFirst<T>(items: T[], key: (item: T) => string, durations: Durations, fallback: (item: T) => number = () => 0): T[] {
  return [...items].sort((a, b) => (durations[key(b)] ?? fallback(b)) - (durations[key(a)] ?? fallback(a)) || key(a).localeCompare(key(b)));
}

export type BaselineChange = { measured: number; added: string[]; dropped: string[] };

export function saveBaseline(root: string = cacheRoot(), baseline: string = BASELINE_DURATIONS, files: string[] = scheduledFiles()): BaselineChange {
  const measured = readDurations(measuredDurationsPath(root));
  const before = readDurations(baseline);
  const known = new Set(files);
  const merged: Durations = Object.fromEntries(Object.entries({ ...before, ...measured }).filter(([file]) => known.has(file)));
  for (const file of missingDurations(files, merged)) merged[file] = UNMEASURED_SECONDS;
  writeFileSync(baseline, `${JSON.stringify(merged, Object.keys(merged).sort(), 2)}
`);
  return { measured: Object.keys(measured).length, added: files.filter((file) => before[file] === undefined).sort(), dropped: Object.keys(before).filter((file) => !known.has(file)).sort() };
}

export function describeChange(change: BaselineChange): string[] {
  const lines = [`scripts/durations.json refreshed from ${change.measured} measured durations`];
  if (change.added.length > 0) lines.push(`  had no entry: ${change.added.join(", ")}`);
  if (change.dropped.length > 0) lines.push(`  dropped, the file is gone: ${change.dropped.join(", ")}`);
  return lines;
}

export function durationsMain(): number {
  if (Object.keys(readDurations(measuredDurationsPath())).length === 0) {
    console.error("no measured durations yet: run npm run check first");
    return 1;
  }
  for (const line of describeChange(saveBaseline())) console.log(line);
  return 0;
}
