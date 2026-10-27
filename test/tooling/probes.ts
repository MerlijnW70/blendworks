import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

export function scratch(prefix: string): string {
  return mkdtempSync(join(tmpdir(), `blendworks-${prefix}-`));
}

export function runProbe(script: string, args: string[]): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((done, fail) => {
    const child = spawn(process.execPath, ["--import", "tsx", resolve("test", "setup", script), ...args], { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", fail);
    child.on("close", (code) => done({ code, stdout, stderr }));
  });
}

export type Interval = { label: string; start: number; end: number };

export function intervals(log: string): Interval[] {
  const starts = new Map<string, number>();
  const out: Interval[] = [];
  for (const line of readFileSync(log, "utf8").split("\n")) {
    const [kind, label, time] = line.split(" ");
    if (label === undefined || time === undefined) continue;
    if (kind === "start") starts.set(label, Number(time));
    if (kind === "end") out.push({ label, start: starts.get(label) ?? Number.NaN, end: Number(time) });
  }
  return out;
}

export function maxOverlap(items: Interval[]): number {
  const edges = items.flatMap((item) => [
    { time: item.start, delta: 1 },
    { time: item.end, delta: -1 },
  ]);
  edges.sort((a, b) => a.time - b.time || a.delta - b.delta);
  let current = 0;
  let best = 0;
  for (const edge of edges) {
    current += edge.delta;
    best = Math.max(best, current);
  }
  return best;
}
