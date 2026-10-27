import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { checkedBlender } from "./blender-check.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { runBlender } from "./run.js";

export const BRIDGE_TESTS = join(repoRoot, "bridge", "tests");
const TIMINGS_FILE = "bridge-timings.json";
const SLOWEST = 5;
const TEST_TIMEOUT_MS = 600_000;

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

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

export function summarize(results: FileResult[], wallSeconds: number): string[] {
  const failed = results.filter((result) => !result.passed).length;
  const slowest = [...results].sort((a, b) => b.seconds - a.seconds).slice(0, SLOWEST);
  const lines = [`${results.length - failed} of ${results.length} bridge test files passed in ${formatSeconds(wallSeconds)}`];
  if (results.length > 1) lines.push(`slowest: ${slowest.map((result) => `${result.file} ${formatSeconds(result.seconds)}`).join(", ")}`);
  return lines;
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
  const started = performance.now();
  const results = await runPool(slowestFirst(selected, timings), jobs, async (file): Promise<FileResult> => {
    const result = await runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(BRIDGE_TESTS, file)], { root, jobs, timeoutMs: TEST_TIMEOUT_MS });
    const passed = result.code === 0 && !result.timedOut;
    const output = passed ? "" : `${result.stdout.slice(-4000)}\n${result.stderr.slice(-2000)}${result.timedOut ? "\ntimed out" : ""}`;
    console.log(`${passed ? "ok  " : "FAIL"} ${file.padEnd(28)} ${formatSeconds(result.seconds)}`);
    if (!passed) console.log(output);
    return { file, passed, seconds: result.seconds, output };
  });
  writeTimings(root, results, timings);
  for (const line of summarize(results, (performance.now() - started) / 1000)) console.log(line);
  return results.every((result) => result.passed) ? 0 : 1;
}
