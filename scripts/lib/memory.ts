import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { totalmem } from "node:os";
import { dirname, join } from "node:path";
import { SCHEDULED_FILE, scheduledFiles } from "./durations.js";
import { cacheRoot, repoRoot } from "./paths.js";

export const BASELINE_PEAKS = join(repoRoot, "scripts", "memory.json");
export const BUDGET_VARIABLE = "BLENDWORKS_MEMORY_BUDGET_MB";
export const GATE_SHARE = 0.6;
export const LARGE_FILE_MB = 2048;
export const HARD_SHARE = 0.85;

export type Peaks = Record<string, number>;

export type MemoryLimit = { mb: number; source: "cgroup memory.max" | "physical memory" };

export type CgroupMemoryFiles = { max: string | undefined; peak: string | undefined; v1Limit: string | undefined; stat?: string | undefined };

function readQuiet(path: string): string | undefined {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return undefined;
  }
}

export function readCgroupMemory(): CgroupMemoryFiles {
  return { max: readQuiet("/sys/fs/cgroup/memory.max"), peak: readQuiet("/sys/fs/cgroup/memory.peak"), v1Limit: readQuiet("/sys/fs/cgroup/memory/memory.limit_in_bytes"), stat: readQuiet("/sys/fs/cgroup/memory.stat") };
}

export function cgroupHeldMb(stat: string | undefined = readQuiet("/sys/fs/cgroup/memory.stat")): number | undefined {
  if (stat === undefined) return undefined;
  const value = (name: string): number | undefined => {
    const match = new RegExp(`^${name} (\\d+)$`, "m").exec(stat);
    return match === null ? undefined : Number(match[1]);
  };
  const anon = value("anon");
  const shmem = value("shmem");
  if (anon === undefined || shmem === undefined) return undefined;
  return Math.round((anon + shmem) / (1024 * 1024));
}

export function hardLimitMb(limit: MemoryLimit = memoryLimit()): number | undefined {
  return limit.source === "cgroup memory.max" ? Math.floor(limit.mb * HARD_SHARE) : undefined;
}

function megabytes(text: string | undefined): number | undefined {
  if (text === undefined || !/^\d+$/.test(text)) return undefined;
  return Number(text) / (1024 * 1024);
}

export function memoryLimit(files: CgroupMemoryFiles = readCgroupMemory(), physicalBytes: number = totalmem()): MemoryLimit {
  const physical = physicalBytes / (1024 * 1024);
  const limit = megabytes(files.max) ?? megabytes(files.v1Limit);
  if (limit !== undefined && limit < physical) return { mb: Math.floor(limit), source: "cgroup memory.max" };
  return { mb: Math.floor(physical), source: "physical memory" };
}

export function cgroupCpuSeconds(stat: string | undefined = readQuiet("/sys/fs/cgroup/cpu.stat")): number | undefined {
  const match = stat === undefined ? null : /^usage_usec (\d+)$/m.exec(stat);
  return match === null ? undefined : Number(match[1]) / 1e6;
}

export function cgroupPeakMb(files: CgroupMemoryFiles = readCgroupMemory()): number | undefined {
  const peak = megabytes(files.peak);
  return peak === undefined ? undefined : Math.round(peak);
}

export function gateBudgetMb(env: NodeJS.ProcessEnv = process.env, limit: MemoryLimit = memoryLimit()): number {
  const text = env[BUDGET_VARIABLE];
  if (text !== undefined && text.trim() !== "") {
    if (!/^\d+$/.test(text.trim()) || Number(text) < 1) throw new Error(`${BUDGET_VARIABLE} must be a whole number of megabytes, not "${text}"`);
    return Number(text);
  }
  return Math.floor(limit.mb * GATE_SHARE);
}

export function measuredPeaksPath(root: string = cacheRoot()): string {
  return join(root, "timings", "memory.json");
}

function readPeaks(path: string): Peaks {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
    if (parsed === null || typeof parsed !== "object") return {};
    return Object.fromEntries(Object.entries(parsed as Record<string, unknown>).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]) && entry[1] >= 0));
  } catch {
    return {};
  }
}

export function knownPeaks(root: string = cacheRoot(), baseline: string = BASELINE_PEAKS): Peaks {
  return { ...readPeaks(baseline), ...readPeaks(measuredPeaksPath(root)) };
}

export function unknownFileMb(peaks: Peaks): number {
  return Math.max(LARGE_FILE_MB, ...Object.values(peaks));
}

export function fileNeedMb(file: string | undefined, peaks: Peaks): number {
  const known = file === undefined ? undefined : peaks[file];
  return known ?? unknownFileMb(peaks);
}

export type Running = { file: string; needMb: number };

export type Live = { heldMb: number; hardMb: number };

export type Refusal = "recorded peaks" | "cgroup memory";

export function refusal(running: Running[], candidate: Running, budgetMb: number, live?: Live): Refusal | undefined {
  const files = new Map<string, number>();
  for (const entry of running) files.set(entry.file, Math.max(files.get(entry.file) ?? 0, entry.needMb));
  if (files.size === 0 || files.has(candidate.file)) return undefined;
  const used = [...files.values()].reduce((sum, need) => sum + need, 0);
  if (used + candidate.needMb > budgetMb) return "recorded peaks";
  return live === undefined || live.heldMb + candidate.needMb <= live.hardMb ? undefined : "cgroup memory";
}

export function admits(running: Running[], candidate: Running, budgetMb: number, live?: Live): boolean {
  return refusal(running, candidate, budgetMb, live) === undefined;
}

function writePeaks(path: string, peaks: Peaks): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(peaks, Object.keys(peaks).sort(), 2)}\n`);
}

export function rememberPeaks(measured: Peaks, root: string = cacheRoot()): Peaks {
  const path = measuredPeaksPath(root);
  const merged = { ...readPeaks(path) };
  for (const [file, mb] of Object.entries(measured)) if (SCHEDULED_FILE.test(file)) merged[file] = Math.round(mb);
  writePeaks(path, merged);
  return merged;
}

export function saveBaselinePeaks(root: string = cacheRoot(), baseline: string = BASELINE_PEAKS, files: string[] = scheduledFiles()): number {
  const merged = { ...readPeaks(baseline), ...readPeaks(measuredPeaksPath(root)) };
  const known = new Set(files);
  const kept = Object.fromEntries(Object.entries(merged).filter(([file]) => known.has(file)));
  writePeaks(baseline, kept);
  return Object.keys(kept).length;
}
