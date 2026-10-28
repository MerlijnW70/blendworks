import { closeSync, fstatSync, openSync, readSync } from "node:fs";
import { EXEMPT_FILES, isExempt } from "./file-limits.js";
import { type WaitTiming } from "./timings.js";

export const PROGRESS_VARIABLE = "BLENDWORKS_PROGRESS";
export const PROGRESS_MARK = "@@blendworks-file ";

export type FileEvent = { event: "start" | "end"; file: string; limited?: boolean; passed?: boolean; seconds?: number };

export type Overdue = { step: string; file: string; seconds: number };

export function announceFile(event: FileEvent, env: NodeJS.ProcessEnv = process.env, write: (line: string) => void = (line) => console.log(line)): void {
  if (env[PROGRESS_VARIABLE] !== "1") return;
  write(`${PROGRESS_MARK}${JSON.stringify(event)}`);
}

export function parseFileEvent(line: string): FileEvent | undefined {
  if (!line.startsWith(PROGRESS_MARK)) return undefined;
  try {
    const value = JSON.parse(line.slice(PROGRESS_MARK.length)) as FileEvent;
    return (value.event === "start" || value.event === "end") && typeof value.file === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

export class LineSplitter {
  private partial = "";

  push(text: string): string[] {
    const pieces = (this.partial + text).split("\n");
    this.partial = pieces.pop() ?? "";
    return pieces.map((piece) => piece.replace(/\r$/, ""));
  }

  rest(): string {
    const rest = this.partial;
    this.partial = "";
    return rest;
  }
}

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

type Running = { startedAt: number; limited: boolean; waitedMs: number; waitingSince: number | undefined };
type StepState = { running: Map<string, Running>; done: number };

export type ProgressOptions = { now: () => number; print: (line: string) => void; limitMs: number; exempt?: Record<string, string> };

export class Progress {
  private readonly steps = new Map<string, StepState>();
  private readonly startedAt: number;

  constructor(private readonly options: ProgressOptions) {
    this.startedAt = options.now();
  }

  stepStarted(step: string): void {
    this.steps.set(step, { running: new Map(), done: 0 });
  }

  stepEnded(step: string): void {
    this.steps.delete(step);
  }

  event(step: string, event: FileEvent): void {
    const state = this.steps.get(step);
    if (state === undefined) return;
    if (event.event === "start") {
      state.running.set(event.file, { startedAt: this.options.now(), limited: event.limited ?? false, waitedMs: 0, waitingSince: undefined });
      return;
    }
    const started = state.running.get(event.file);
    state.running.delete(event.file);
    state.done += 1;
    const seconds = event.seconds ?? (started === undefined ? 0 : (this.options.now() - started.startedAt) / 1000);
    this.options.print(`${event.passed === false ? "FAIL" : "ok  "} [${step}] ${event.file} ${seconds.toFixed(1)} s`);
  }

  waiting(wait: WaitTiming): void {
    const now = this.options.now();
    for (const state of this.steps.values()) {
      const entry = state.running.get(wait.file);
      if (entry === undefined) continue;
      if (wait.state === "begin") entry.waitingSince ??= now;
      else {
        entry.waitedMs += wait.waitedMs ?? (entry.waitingSince === undefined ? 0 : now - entry.waitingSince);
        entry.waitingSince = undefined;
      }
    }
  }

  heartbeat(): void {
    const now = this.options.now();
    const parts = [...this.steps].map(([step, state]) => {
      const running = [...state.running].map(([file, entry]) => `${file} ${Math.round((now - entry.startedAt) / 1000)} s`);
      const done = state.done > 0 ? `${state.done} done` : "";
      const detail = [done, running.length > 0 ? `running ${running.join(", ")}` : ""].filter((text) => text !== "").join("; ");
      return detail === "" ? step : `${step} (${detail})`;
    });
    this.options.print(`still running ${clock((now - this.startedAt) / 1000)}: ${parts.join(", ")}`);
  }

  overdue(): Overdue[] {
    const now = this.options.now();
    const exempt = this.options.exempt ?? EXEMPT_FILES;
    const late: Overdue[] = [];
    for (const [step, state] of this.steps) {
      for (const [file, entry] of state.running) {
        const workedMs = now - entry.startedAt - entry.waitedMs - (entry.waitingSince === undefined ? 0 : now - entry.waitingSince);
        if (entry.limited && !isExempt(file, exempt) && workedMs > this.options.limitMs) late.push({ step, file, seconds: workedMs / 1000 });
      }
    }
    return late;
  }
}

export class WaitLog {
  private offset = 0;
  private partial = "";

  constructor(private readonly path: string | undefined) {}

  poll(): WaitTiming[] {
    if (this.path === undefined || this.path === "") return [];
    let descriptor: number;
    try {
      descriptor = openSync(this.path, "r");
    } catch {
      return [];
    }
    try {
      const size = fstatSync(descriptor).size;
      if (size <= this.offset) return [];
      const buffer = Buffer.alloc(size - this.offset);
      const read = readSync(descriptor, buffer, 0, buffer.length, this.offset);
      this.offset += read;
      const pieces = (this.partial + buffer.subarray(0, read).toString("utf8")).split("\n");
      this.partial = pieces.pop() ?? "";
      return pieces.flatMap((piece) => {
        try {
          const value = JSON.parse(piece) as WaitTiming;
          return value.kind === "wait" ? [value] : [];
        } catch {
          return [];
        }
      });
    } finally {
      closeSync(descriptor);
    }
  }
}

export function overdueReason(late: Overdue, limitMs: number): string {
  return `FAIL ${late.file} worked ${late.seconds.toFixed(1)} s, past its limit of ${limitMs / 1000} s per test file (time waiting for a Blender slot does not count) (BLENDWORKS_FILE_LIMIT_S); step ${late.step} was stopped. A file that needs longer is listed with its reason in scripts/lib/file-limits.ts`;
}
