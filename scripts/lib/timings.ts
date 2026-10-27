import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname } from "node:path";

export const TIMINGS_VARIABLE = "BLENDWORKS_TIMINGS";
export const STAGE_VARIABLE = "BLENDWORKS_STAGE";

export type ProcessTiming = { kind: "process"; stage: string; label: string; waitMs: number; workMs: number; endedAt: number };
export type FileTiming = { kind: "file"; stage: string; file: string; wallMs: number; waitMs: number; processes: number; endedAt: number };
export type Timing = ProcessTiming | FileTiming;

export function currentStage(env: NodeJS.ProcessEnv = process.env): string {
  const stage = env[STAGE_VARIABLE];
  return stage === undefined || stage === "" ? "manual" : stage;
}

export function recordTiming(timing: Timing, env: NodeJS.ProcessEnv = process.env): void {
  const path = env[TIMINGS_VARIABLE];
  if (path === undefined || path === "") return;
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(timing)}\n`);
}

export function readTimingLog(path: string): Timing[] {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch {
    return [];
  }
  const out: Timing[] = [];
  for (const line of text.split("\n")) {
    if (line.trim() === "") continue;
    try {
      out.push(JSON.parse(line) as Timing);
    } catch {
      continue;
    }
  }
  return out;
}

export type StageTotals = { stage: string; processes: number; workSeconds: number; waitSeconds: number };

export function stageTotals(timings: Timing[]): StageTotals[] {
  const totals = new Map<string, StageTotals>();
  for (const timing of timings) {
    if (timing.kind !== "process") continue;
    const entry = totals.get(timing.stage) ?? { stage: timing.stage, processes: 0, workSeconds: 0, waitSeconds: 0 };
    entry.processes += 1;
    entry.workSeconds += timing.workMs / 1000;
    entry.waitSeconds += timing.waitMs / 1000;
    totals.set(timing.stage, entry);
  }
  return [...totals.values()].sort((a, b) => b.workSeconds - a.workSeconds);
}

export function slowestFiles(timings: Timing[], count: number): FileTiming[] {
  return timings
    .filter((timing): timing is FileTiming => timing.kind === "file")
    .sort((a, b) => b.wallMs - a.wallMs)
    .slice(0, count);
}

function seconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

export function timingReport(timings: Timing[], wallSeconds: number, jobs: number, count = 8): string[] {
  const files = slowestFiles(timings, count);
  const totals = stageTotals(timings);
  if (files.length === 0 && totals.length === 0) return [];
  const lines = [`slowest files (wall, of which waiting for a Blender slot):`];
  for (const file of files) lines.push(`  ${seconds(file.wallMs).padStart(8)}  wait ${seconds(file.waitMs).padStart(8)}  ${file.processes} Blender  ${file.stage}  ${file.file}`);
  const work = totals.reduce((sum, entry) => sum + entry.workSeconds, 0);
  for (const entry of totals) lines.push(`Blender in ${entry.stage}: ${entry.processes} processes, ${entry.workSeconds.toFixed(0)} s working, ${entry.waitSeconds.toFixed(0)} s waiting for a slot`);
  if (wallSeconds > 0) lines.push(`slots busy ${Math.round((100 * work) / (jobs * wallSeconds))} % of ${jobs} x ${wallSeconds.toFixed(0)} s`);
  return lines;
}
