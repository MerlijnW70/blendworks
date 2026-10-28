import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { checkedBlender } from "./blender-check.js";
import { knownDurations } from "./durations.js";
import { fileLimitMs, isExempt } from "./file-limits.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { announceFile } from "./progress.js";
import { runBlender, type RunOptions, type RunResult } from "./run.js";
import { currentStage, recordTiming } from "./timings.js";

export const BRIDGE_TESTS = join(repoRoot, "bridge", "tests");
const TIMINGS_FILE = "bridge-timings.json";
const SLOWEST = 5;

export type FileResult = { file: string; passed: boolean; seconds: number; output: string };

export function listBridgeTests(directory: string = BRIDGE_TESTS): string[] {
  return existsSync(directory) ? readdirSync(directory).filter((name) => /^test_.*\.py$/.test(name)).sort() : [];
}

function matches(file: string, filter: string): boolean {
  const wanted = filter.split("\\").join("/").split("/").pop() ?? filter;
  const stem = file.replace(/\.py$/, "");
  if (wanted === file || wanted === stem) return true;
  return stem.includes(wanted.replace(/\.py$/, ""));
}

export function selectTests(all: string[], filters: string[]): string[] {
  if (filters.length === 0) return [...all];
  return all.filter((file) => filters.some((filter) => matches(file, filter)));
}

export async function runPool<T, R>(items: T[], limit: number, worker: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  async function lane(): Promise<void> {
    for (;;) {
      const index = next;
      next += 1;
      if (index >= items.length) return;
      results[index] = await worker(items[index] as T);
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, lane));
  return results;
}

export function slowestFirst(files: string[], timings: Record<string, number>): string[] {
  return [...files].sort((a, b) => (timings[b] ?? Number.POSITIVE_INFINITY) - (timings[a] ?? Number.POSITIVE_INFINITY) || a.localeCompare(b));
}

export function readTimings(root: string): Record<string, number> {
  try {
    return JSON.parse(readFileSync(join(root, TIMINGS_FILE), "utf8")) as Record<string, number>;
  } catch {
    return {};
  }
}

function writeTimings(root: string, results: FileResult[], previous: Record<string, number>): void {
  const merged = { ...previous };
  for (const result of results) merged[result.file] = result.seconds;
  mkdirSync(root, { recursive: true });
  writeFileSync(join(root, TIMINGS_FILE), JSON.stringify(merged));
}

export function bridgeDurations(durations: Record<string, number>): Record<string, number> {
  const prefix = "bridge/tests/";
  return Object.fromEntries(Object.entries(durations).filter(([key]) => key.startsWith(prefix)).map(([key, seconds]) => [key.slice(prefix.length), seconds]));
}

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

export function timeoutLine(file: string, result: Pick<RunResult, "seconds" | "waitedSeconds">, stage: string = currentStage(), limitMs: number = fileLimitMs()): string {
  return `timed out working, not waiting: ${file} in stage ${stage} worked ${formatSeconds(result.seconds)}, over its limit of ${limitMs / 1000} s; it waited ${formatSeconds(result.waitedSeconds)} for a Blender slot before it started, which does not count`;
}

export function summarize(results: FileResult[], wallSeconds: number): string[] {
  const failed = results.filter((result) => !result.passed).length;
  const slowest = [...results].sort((a, b) => b.seconds - a.seconds).slice(0, SLOWEST);
  const lines = [`${results.length - failed} of ${results.length} bridge test files passed in ${formatSeconds(wallSeconds)}`];
  if (results.length > 1) lines.push(`slowest: ${slowest.map((result) => `${result.file} ${formatSeconds(result.seconds)}`).join(", ")}`);
  return lines;
}

export async function runBridgeFile(file: string, launch: (file: string, options: RunOptions) => Promise<RunResult>, env: NodeJS.ProcessEnv = process.env): Promise<FileResult> {
  const key = `bridge/tests/${file}`;
  const limitMs = fileLimitMs(env);
  const result = await launch(file, { ...(isExempt(key) ? {} : { timeoutMs: limitMs }), onStart: () => announceFile({ event: "start", file: key }, env) });
  const passed = result.code === 0 && !result.timedOut;
  const output = passed ? "" : `${result.stdout.slice(-4000)}
${result.stderr.slice(-2000)}${result.timedOut ? `
${timeoutLine(file, result, currentStage(env), limitMs)}` : ""}`;
  announceFile({ event: "end", file: key, passed, seconds: result.seconds }, env);
  console.log(`${passed ? "ok  " : "FAIL"} ${file.padEnd(28)} ${formatSeconds(result.seconds)}`);
  if (!passed) console.log(output);
  recordTiming({ kind: "file", stage: currentStage(env), file: key, wallMs: Math.round((result.seconds + result.waitedSeconds) * 1000), waitMs: Math.round(result.waitedSeconds * 1000), processes: 1, endedAt: Date.now() }, env);
  return { file, passed, seconds: result.seconds, output };
}

export async function bridgeMain(argv: string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const filters = argv.filter((argument) => !argument.startsWith("-"));
  const unknown = argv.filter((argument) => argument.startsWith("-"));
  if (unknown.length > 0) {
    console.error(`unknown option ${unknown[0]}; usage: npm run test:bridge -- [name ...]  (a name is part of a file name, such as test_render or render)`);
    return 2;
  }
  const all = listBridgeTests();
  const selected = selectTests(all, filters);
  if (selected.length === 0) {
    console.error(`no bridge test file matches ${filters.join(", ")}; the files are ${all.join(", ")}`);
    return 1;
  }
  const root = ensureCacheRoot(cacheRoot(env));
  const blender = checkedBlender(root);
  const jobs = blenderJobs(env);
  const timings = readTimings(root);
  const expected = { ...bridgeDurations(knownDurations(root)), ...timings };
  const started = performance.now();
  const launch = (file: string, options: RunOptions) => runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(BRIDGE_TESTS, file)], { root, jobs, label: file, ...options });
  const results = await runPool(slowestFirst(selected, expected), jobs, (file) => runBridgeFile(file, launch, env));
  writeTimings(root, results, timings);
  for (const line of summarize(results, (performance.now() - started) / 1000)) console.log(line);
  return results.every((result) => result.passed) ? 0 : 1;
}
