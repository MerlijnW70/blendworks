import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { checkedBlender } from "./blender-check.js";
import { bridgeSharing, freshReason, harnessOutcomes, SharedStream, takeWork, type TestOutcome } from "./bridge-shared.js";
import { knownDurations } from "./durations.js";
import { fileLimitMs, isExempt } from "./file-limits.js";
import { fileNeedMb, knownPeaks } from "./memory.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { buildNative, nativeRequired, nativeVerdict } from "./native-build.js";
import { announceFile } from "./progress.js";
import { runBlender, type RunOptions, type RunResult } from "./run.js";
import { currentStage, recordTiming } from "./timings.js";

export const BRIDGE_TESTS = join(repoRoot, "bridge", "tests");
const TIMINGS_FILE = "bridge-timings.json";
const SLOWEST = 5;

export type FileResult = { file: string; passed: boolean; seconds: number; output: string; tests?: TestOutcome[] };

export const SHARED_HELPER = join(BRIDGE_TESTS, "shared.py");

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

export const TESTS_VARIABLE = "BLENDWORKS_BRIDGE_TESTS";
export const DEVICE_VARIABLE = "BLENDWORKS_DEVICE";

export function testEnvironment(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  return { ...env, [DEVICE_VARIABLE]: env[DEVICE_VARIABLE] === undefined || env[DEVICE_VARIABLE] === "" ? "cpu" : env[DEVICE_VARIABLE] };
}

export function bridgeTestsDirectory(env: NodeJS.ProcessEnv = process.env): string {
  const chosen = env[TESTS_VARIABLE];
  return chosen === undefined || chosen === "" ? BRIDGE_TESTS : resolve(chosen);
}

export function bridgeKey(file: string, directory: string = BRIDGE_TESTS): string {
  return relative(repoRoot, join(directory, file)).split(sep).join("/");
}

function finishFile(file: string, key: string, passed: boolean, seconds: number, waitedSeconds: number, processes: number, output: string, tests: TestOutcome[], env: NodeJS.ProcessEnv): FileResult {
  announceFile({ event: "end", file: key, passed, seconds }, env);
  console.log(`${passed ? "ok  " : "FAIL"} ${file.padEnd(28)} ${formatSeconds(seconds)}`);
  if (!passed) console.log(output);
  recordTiming({ kind: "file", stage: currentStage(env), file: key, wallMs: Math.round((seconds + waitedSeconds) * 1000), waitMs: Math.round(waitedSeconds * 1000), processes, endedAt: Date.now() }, env);
  recordTiming({ kind: "result", stage: currentStage(env), file: key, passed, tests }, env);
  return { file, passed, seconds, output: passed ? "" : output, tests };
}

export async function runBridgeFile(file: string, launch: (file: string, options: RunOptions) => Promise<RunResult>, env: NodeJS.ProcessEnv = process.env, directory: string = BRIDGE_TESTS): Promise<FileResult> {
  const key = bridgeKey(file, directory);
  const limitMs = fileLimitMs(env);
  const result = await launch(file, { ...(isExempt(key) ? {} : { timeoutMs: limitMs }), onStart: () => announceFile({ event: "start", file: key }, env) });
  const passed = result.code === 0 && !result.timedOut;
  const output = `${result.stdout.slice(-4000)}
${result.stderr.slice(-2000)}${result.timedOut ? `
${timeoutLine(file, result, currentStage(env), limitMs)}` : ""}`;
  return finishFile(file, key, passed, result.seconds, result.waitedSeconds, 1, output, harnessOutcomes(result.stdout), env);
}

export type SharedLaunch = (files: string[], options: RunOptions) => Promise<RunResult>;

export async function runSharedBatch(files: string[], launch: SharedLaunch, env: NodeJS.ProcessEnv = process.env, directory: string = BRIDGE_TESTS): Promise<{ results: FileResult[]; rest: string[] }> {
  const limitMs = fileLimitMs(env);
  const results: FileResult[] = [];
  const stopper = new AbortController();
  let attach: ((file: string) => void) | undefined;
  let current: { file: string; started: number; timer: NodeJS.Timeout | undefined } | undefined;
  let overran: { file: string; seconds: number } | undefined;
  let waitedSeconds = 0;
  let firstFile = true;
  const share = (): { wait: number; processes: number } => {
    const out = firstFile ? { wait: waitedSeconds, processes: 1 } : { wait: 0, processes: 0 };
    firstFile = false;
    return out;
  };
  const stream = new SharedStream(
    (file) => {
      const key = bridgeKey(file, directory);
      announceFile({ event: "start", file: key }, env);
      attach?.(key);
      const started = performance.now();
      const timer = isExempt(key)
        ? undefined
        : setTimeout(() => {
            overran = { file, seconds: (performance.now() - started) / 1000 };
            stopper.abort();
          }, limitMs);
      current = { file, started, timer };
    },
    (event, output) => {
      if (current?.file !== event.file) return;
      clearTimeout(current.timer);
      const seconds = (performance.now() - current.started) / 1000;
      current = undefined;
      const { wait, processes } = share();
      results.push(finishFile(event.file, bridgeKey(event.file, directory), event.passed, seconds, wait, processes, output, harnessOutcomes(output), env));
    },
  );
  const result = await launch(files, {
    signal: stopper.signal,
    onStart: () => undefined,
    onSpawn: (pid, slot) => {
      attach = (key) => slot?.attach(pid, key, true);
    },
    onStdout: (chunk) => stream.push(chunk),
  });
  waitedSeconds = result.waitedSeconds;
  const unfinished = stream.unfinished();
  const done = new Set(results.map((entry) => entry.file));
  const broken = unfinished?.file ?? (results.length === 0 ? files[0] : undefined);
  if (broken !== undefined) {
    clearTimeout(current?.timer);
    const seconds = current === undefined ? result.seconds : (performance.now() - current.started) / 1000;
    const why =
      overran?.file === broken
        ? timeoutLine(broken, { seconds: overran.seconds, waitedSeconds: 0 }, currentStage(env), limitMs)
        : `Blender ended during ${broken} (exit code ${result.code ?? result.signal}) in a shared process; files after it run in a new process`;
    const { wait, processes } = share();
    results.push(finishFile(broken, bridgeKey(broken, directory), false, seconds, wait, processes, `${unfinished?.output ?? result.stdout.slice(-4000)}\n${result.stderr.slice(-2000)}\n${why}`, harnessOutcomes(unfinished?.output ?? ""), env));
    done.add(broken);
  }
  return { results, rest: files.filter((file) => !done.has(file)) };
}

export async function bridgeMain(argv: string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const filters = argv.filter((argument) => !argument.startsWith("-"));
  const unknown = argv.filter((argument) => argument.startsWith("-"));
  if (unknown.length > 0) {
    console.error(`unknown option ${unknown[0]}; usage: npm run test:bridge -- [name ...]  (a name is part of a file name, such as test_render or render)`);
    return 2;
  }
  const directory = bridgeTestsDirectory(env);
  const all = listBridgeTests(directory);
  const selected = selectTests(all, filters);
  if (selected.length === 0) {
    console.error(`no bridge test file matches ${filters.join(", ")}; the files are ${all.join(", ")}`);
    return 1;
  }
  const native = nativeVerdict(buildNative(env), nativeRequired(env));
  if (native.code !== 0) {
    console.error(`the bridge tests cannot run: ${native.message}`);
    return 1;
  }
  console.log(native.message.split(/\r?\n/)[0]);
  const root = ensureCacheRoot(cacheRoot(env));
  const blender = checkedBlender(root);
  const jobs = blenderJobs(env);
  const timings = readTimings(root);
  const expected = { ...bridgeDurations(knownDurations(root)), ...timings };
  const started = performance.now();
  const peaks = knownPeaks(root);
  const needMb = (file: string): number => fileNeedMb(bridgeKey(file, directory), peaks);
  const launch = (file: string, options: RunOptions) => runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(directory, file)], { root, jobs, label: file, file: bridgeKey(file, directory), needMb: needMb(file), env: testEnvironment(env), ...options });
  const launchShared: SharedLaunch = (files, options) =>
    runBlender(blender.path, ["--background", "--factory-startup", "--python", SHARED_HELPER, "--", ...files.map((file) => join(directory, file))], { root, jobs, label: files.length === 1 ? (files[0] as string) : `${files[0]} and ${files.length - 1} more`, file: bridgeKey(files[0] as string, directory), needMb: Math.max(...files.map(needMb)), env: testEnvironment(env), ...options });
  const sharing = bridgeSharing(env);
  const fresh = new Map(selected.map((file) => [file, sharing.shared ? freshReason(file, directory) : sharing.reason]));
  const freshCount = [...fresh.values()].filter((reason) => reason !== undefined).length;
  console.log(sharing.shared ? `${selected.length - freshCount} bridge test files share Blender processes with a factory reset between files; ${freshCount} keep their own` : `every bridge test file gets a fresh Blender: ${sharing.reason}`);
  const queue = slowestFirst(selected, expected);
  const results: FileResult[] = [];
  await runPool(Array.from({ length: Math.max(1, Math.min(jobs, selected.length)) }, (_, lane) => lane), jobs, async () => {
    for (let work = takeWork(queue, (file) => fresh.get(file) === undefined, expected); work !== undefined; work = takeWork(queue, (file) => fresh.get(file) === undefined, expected)) {
      if (work.kind === "fresh") {
        results.push(await runBridgeFile(work.file, launch, env, directory));
        continue;
      }
      const batch = await runSharedBatch(work.files, launchShared, env, directory);
      results.push(...batch.results);
      queue.unshift(...batch.rest);
    }
  });
  if (directory === BRIDGE_TESTS) writeTimings(root, results, timings);
  for (const line of summarize(results, (performance.now() - started) / 1000)) console.log(line);
  return results.every((result) => result.passed) ? 0 : 1;
}
