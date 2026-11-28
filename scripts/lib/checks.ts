import { join } from "node:path";
import { blenderJobs, thisMachine } from "../../src/blender.js";
import { execFileSync } from "node:child_process";
import { describeChange, rememberDurations, saveBaseline } from "./durations.js";
import { affectedPhases, chooseAffected, parseAffectedArgs, selectionLines } from "./affected-check.js";
import { cgroupCpuSeconds, cgroupPeakMb, gateBudgetMb, memoryLimit, rememberPeaks, saveBaselinePeaks, type Peaks } from "./memory.js";
import { startMemoryMeter } from "./memory-meter.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { npmStep, runPhases, type Step, VITEST_REPORTERS } from "./pipeline.js";
import { bridgePassList, mergePassLists, passListLines, readVitestPassList, writePassList } from "./pass-list.js";
import { slotsDirectory } from "./slots.js";
import { readTimingLog, timingReport, TIMINGS_VARIABLE } from "./timings.js";

export function vitestReporters(report?: string): string[] {
  return report === undefined ? VITEST_REPORTERS : [...VITEST_REPORTERS, "--reporter=json", `--outputFile.json=${report}`];
}

export function fullPhases(report?: string): Step[][] {
  return [[npmStep("rules"), npmStep("typecheck"), npmStep("build"), npmStep("build:addon"), npmStep("test", [], {}, vitestReporters(report)), npmStep("test:bridge")]];
}

export function timingLogPath(name: string, env: NodeJS.ProcessEnv = process.env): string {
  return join(cacheRoot(env), "timings", `${name}-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`);
}

function git(args: string[]): string {
  try {
    return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "?";
  }
}

export function onCleanMain(): boolean {
  return git(["rev-parse", "--abbrev-ref", "HEAD"]) === "main" && git(["status", "--porcelain"]) === "";
}

export function memoryReport(peaks: Peaks, budgetMb: number, limitMb: number, limitSource: string, cgroupPeak: number | undefined, count = 3): string[] {
  const largest = Object.entries(peaks)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, count);
  const lines = [`memory gate: ${budgetMb} MB of ${limitMb} MB (${limitSource}) for the recorded peaks of running files; ${Object.keys(peaks).length} files measured`];
  if (largest.length > 0) lines.push(`largest file peaks: ${largest.map(([file, mb]) => `${file} ${mb} MB`).join(", ")}`);
  if (cgroupPeak !== undefined) lines.push(`cgroup memory.peak ${cgroupPeak} MB of ${limitMb} MB`);
  return lines;
}

async function timedPhases(name: string, phases: (vitestReport: string) => Step[][], refreshBaseline = false): Promise<boolean> {
  const log = timingLogPath(name);
  process.env[TIMINGS_VARIABLE] = log;
  const root = ensureCacheRoot(cacheRoot());
  const vitestReport = log.replace(/\.jsonl$/, "-vitest.json");
  const meter = startMemoryMeter(slotsDirectory(root));
  const cpuBefore = cgroupCpuSeconds();
  const { passed, seconds } = await runPhases(phases(vitestReport));
  const cpuAfter = cgroupCpuSeconds();
  const peaks = meter?.stop() ?? {};
  const timings = readTimingLog(log);
  for (const line of timingReport(timings, seconds, blenderJobs())) console.log(line);
  const passList = mergePassLists(readVitestPassList(vitestReport), bridgePassList(timings));
  const passListPath = log.replace(/\.jsonl$/, "-pass-list.json");
  writePassList(passList, passListPath);
  for (const line of passListLines(passList, passListPath)) console.log(line);
  const limit = memoryLimit();
  for (const line of memoryReport(peaks, gateBudgetMb(), limit.mb, limit.source, cgroupPeakMb())) console.log(line);
  if (cpuBefore !== undefined && cpuAfter !== undefined) console.log(`cgroup CPU time ${(cpuAfter - cpuBefore).toFixed(0)} s over ${seconds.toFixed(0)} s on ${thisMachine().cpus} CPUs: ${Math.round((100 * (cpuAfter - cpuBefore)) / (seconds * thisMachine().cpus))} % used; the CPU time alone needs ${((cpuAfter - cpuBefore) / thisMachine().cpus / 60).toFixed(1)} min`);
  rememberDurations(timings);
  rememberPeaks(peaks, root);
  if (passed && refreshBaseline) {
    for (const line of describeChange(saveBaseline())) console.log(line);
    saveBaselinePeaks(root);
  }
  return passed;
}

export async function checkMain(): Promise<number> {
  return (await timedPhases("check", (report) => fullPhases(report), onCleanMain())) ? 0 : 1;
}

export async function affectedMain(argv: string[] = process.argv.slice(2)): Promise<number> {
  const args = parseAffectedArgs(argv);
  if (typeof args === "string") {
    console.error(args);
    return 2;
  }
  const started = performance.now();
  const { base, selection, blender } = chooseAffected(args);
  for (const line of selectionLines(base, selection, blender)) console.log(line);
  console.log(`selected in ${((performance.now() - started) / 1000).toFixed(1)} s`);
  if (args.dryRun) return 0;
  return (await timedPhases("check-affected", (report) => affectedPhases(selection, vitestReporters(report)))) ? 0 : 1;
}
