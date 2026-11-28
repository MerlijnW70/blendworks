import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { repoRoot } from "./paths.js";

export const WALL_CLOCK_ALLOWED: Record<string, string> = {
  "test/mcp-routing-bench.test.ts": "the 20 ms query bound counts the CPU time of the search (process.cpuUsage), which a busy host does not stretch",
  "test/mcp-connection.test.ts": "it tells a 150 ms timeout from the 5 s default with a 3 s bound and no Blender: a 20-fold margin over the timer",
  "test/mcp-long-calls.test.ts": "it tells 0.2 s and 150 ms timers from a hang with 3 s and 1 s bounds over fake bridges, without Blender or slots",
  "test/judge/sandbox.test.ts": "the 30 s bound for an 8 s timeout subtracts the time spent waiting for a Blender slot",
  "test/package/native-run.test.ts": "it tells an 800 ms timeout on a Node process from a hang with a 15 s bound, without Blender or slots",
};

const UPPER_BOUND = /\.(toBeLessThan|toBeLessThanOrEqual)\(/;
const TIME_WORDS = /performance\.now|Date\.now|hrtime|\bseconds\b|elapsed|\bduration\b|waited|\btook\b|\bms\b/i;
const TIME_NAMES = /[a-z]Ms\b|_MS\b/;

export type WallClockBound = { line: number; text: string };

export function wallClockBounds(source: string): WallClockBound[] {
  const found: WallClockBound[] = [];
  source.split("\n").forEach((text, index) => {
    if (UPPER_BOUND.test(text) && (TIME_WORDS.test(text) || TIME_NAMES.test(text))) found.push({ line: index + 1, text: text.trim() });
  });
  return found;
}

export function testSources(directory: string = join(repoRoot, "test"), prefix = "test/"): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return name === "node_modules" ? [] : testSources(path, `${prefix}${name}/`);
    return /\.ts$/.test(name) ? [`${prefix}${name}`] : [];
  });
}

export function offendingFiles(): Record<string, WallClockBound[]> {
  const out: Record<string, WallClockBound[]> = {};
  for (const file of testSources()) {
    if (file === "test/tooling/wall-clock-lint.test.ts") continue;
    const bounds = wallClockBounds(readFileSync(join(repoRoot, file), "utf8"));
    if (bounds.length > 0) out[file] = bounds;
  }
  return out;
}

export const LIVE_CLOCK = /\btime\.(perf_counter|time|monotonic)\(\)/;
export const HOST_PROBE = /\b(freemem|loadavg|availableParallelism|cpu_count|available_memory|available_cpus|meminfo_available|GlobalMemoryStatusEx)\s*\(\s*\)/;

export const LIVE_READING_ALLOWED: Record<string, string> = {
  "bridge/tests/fluvial_speed.py": "it compares a single-threaded run with a single-threaded calibration measured in the same process just before, takes the fastest of three, and compares the ratio with the recorded one",
  "bridge/tests/shared.py": "it times each file for the runner's records and asserts nothing about the time",
  "bridge/tests/terrain_speed.py": "it compares each kernel with a calibration measured in the same process just before, takes the fastest of five runs, and allows a factor of four",
  "bridge/tests/test_addon.py": "a deadline on waiting for the add-on server to answer, not a bound on work",
  "bridge/tests/test_autosave_bench.py": "the wall times are printed; the overhead target compares main-thread CPU time",
  "bridge/tests/test_scene_info.py": "the elapsed time is printed, not asserted",
  "bridge/tests/test_world_scale.py": "limits.available_memory() reads the cgroup limit and the physical memory, which do not change with load, and the test compares the module constant with the same reading",
  "test/setup/cpu-quota.ts": "it sizes the Blender threads of a test from the CPUs, as the runner does, and asserts nothing",
  "test/tooling/session-threads.test.ts": "it computes the expected thread count from the same CPU count the code under test reads",
};

export type LiveReading = { file: string; line: number; text: string };

export function liveReadings(source: string, file: string): LiveReading[] {
  const python = file.endsWith(".py");
  const found: LiveReading[] = [];
  source.split("\n").forEach((text, index) => {
    if ((python && LIVE_CLOCK.test(text)) || HOST_PROBE.test(text)) found.push({ file, line: index + 1, text: text.trim() });
  });
  return found;
}

export function liveReadingFiles(): Record<string, LiveReading[]> {
  const bridge = readdirSync(join(repoRoot, "bridge", "tests")).filter((name) => name.endsWith(".py")).map((name) => `bridge/tests/${name}`);
  const out: Record<string, LiveReading[]> = {};
  for (const file of [...bridge, ...testSources()]) {
    if (file === "test/tooling/wall-clock-lint.test.ts") continue;
    const found = liveReadings(readFileSync(join(repoRoot, file), "utf8"), file);
    if (found.length > 0) out[file] = found;
  }
  return out;
}
