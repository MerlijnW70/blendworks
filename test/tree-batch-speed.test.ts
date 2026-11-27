import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Task = { tree: number; worker: number; build: number; write: number; merge: number };
type Record = { report: { workers: number; fallbacks: unknown[]; tasks: Task[]; worker_startup_seconds: number[]; worker_peak_memory: number; worker_memory_estimate: number } };

const JUDGE_WORKERS = 4;
const TARGET = 1.7;

function scheduleSeconds(tasks: Task[], workers: number, startup: number): number {
  const free = Array.from({ length: workers }, () => startup);
  let merged = 0;
  for (const task of [...tasks].sort((a, b) => a.tree - b.tree)) {
    const worker = free.indexOf(Math.min(...free));
    const finished = (free[worker] ?? startup) + task.build + task.write;
    free[worker] = finished;
    merged = Math.max(merged, finished) + task.merge;
  }
  return merged;
}

describe("the tree batch on the check-size tree set", workBudget(420_000), () => {
  it("would build at least 1.7 times faster with four workers than one after another, from the work one worker measures", () => {
    const out = freshDir("tree-batch-speed");
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python", "bench/trees/bench.py", "--", out, "parallel", "--workers", "1"], { stdio: "pipe" });
    const record = JSON.parse(readFileSync(join(out, "parallel.json"), "utf8")) as Record;
    const { tasks, fallbacks, worker_startup_seconds: startups } = record.report;
    expect(fallbacks).toEqual([]);
    expect(tasks.map((task) => task.tree)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(record.report.worker_peak_memory).toBeLessThan(record.report.worker_memory_estimate);
    const serial = tasks.reduce((sum, task) => sum + task.build, 0);
    const startup = Math.max(...startups);
    expect(scheduleSeconds(tasks, 1, startup)).toBeGreaterThanOrEqual(serial);
    const speedup = serial / scheduleSeconds(tasks, JUDGE_WORKERS, startup);
    expect(speedup, `speedup ${speedup.toFixed(2)} with ${JUDGE_WORKERS} workers`).toBeGreaterThanOrEqual(TARGET);
  });
});
