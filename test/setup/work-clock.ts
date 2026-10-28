import { observeWaits } from "../../scripts/lib/locks.js";
import { observeAcquisitions } from "../../scripts/lib/slots.js";
import { relative, sep } from "node:path";
import { expect } from "vitest";
import { currentStage } from "../../scripts/lib/timings.js";

export function testFile(): string {
  return relative(process.cwd(), expect.getState().testPath ?? "").split(sep).join("/");
}

export const WAIT_FOR_SLOT_MS = 45 * 60_000;
export const ENVELOPE_GRACE_MS = 60_000;

export type Timers = { now(): number; after(ms: number, run: () => void): () => void };

export const realTimers: Timers = {
  now: () => performance.now(),
  after(ms, run) {
    const timer = setTimeout(run, ms);
    return () => clearTimeout(timer);
  },
};

let timers: Timers = realTimers;

export function useTimers(next: Timers): () => void {
  const previous = timers;
  timers = next;
  return () => {
    timers = previous;
  };
}

let pending = 0;
let pendingSince = 0;
let settledWaitMs = 0;
const listeners = new Set<() => void>();

function waitedSoFar(now: number = timers.now()): number {
  return settledWaitMs + (pending > 0 ? now - pendingSince : 0);
}

function notify(): void {
  for (const listener of [...listeners]) listener();
}

let acquisitions = 0;

observeAcquisitions(() => {
  acquisitions += 1;
});

observeWaits({
  waiting() {
    if (pending === 0) pendingSince = timers.now();
    pending += 1;
    notify();
  },
  waited() {
    pending -= 1;
    if (pending === 0) settledWaitMs += timers.now() - pendingSince;
    notify();
  },
});

export function slotTotals(): { waitMs: number; acquisitions: number } {
  return { waitMs: waitedSoFar(), acquisitions };
}

export function waitingForSlot(): boolean {
  return pending > 0;
}

export class WorkTimeout extends Error {
  constructor(
    readonly label: string,
    readonly budgetMs: number,
    readonly workMs: number,
    readonly waitMs: number,
  ) {
    super(
      `timed out working, not waiting: ${label} in stage ${currentStage()} worked ${(workMs / 1000).toFixed(1)} s, over its work budget of ${budgetMs / 1000} s; ` +
        `it also waited ${(waitMs / 1000).toFixed(1)} s for a Blender slot or a lock, which does not count`,
    );
  }
}

export type WorkClock = { label: string; budgetMs: number; workMs(): number; waitMs(): number; waitAllowanceMs(): number; expired: Promise<never>; stop(): void };

export function startWorkClock(label: string, budgetMs: number): WorkClock {
  const now = (): number => timers.now();
  const started = now();
  const waitAtStart = waitedSoFar(started);
  let cancelTimer: () => void = () => undefined;
  let fail: (error: WorkTimeout) => void = () => undefined;
  const expired = new Promise<never>((_, reject) => {
    fail = reject;
  });
  expired.catch(() => undefined);
  const waitMs = (): number => waitedSoFar(now()) - waitAtStart;
  const workMs = (): number => now() - started - waitMs();
  const schedule = (): void => {
    cancelTimer();
    cancelTimer = () => undefined;
    if (pending > 0) return;
    const left = budgetMs - workMs();
    if (left <= 0) {
      stop();
      fail(new WorkTimeout(label, budgetMs, workMs(), waitMs()));
      return;
    }
    cancelTimer = timers.after(Math.ceil(left), schedule);
  };
  const stop = (): void => {
    cancelTimer();
    listeners.delete(schedule);
  };
  listeners.add(schedule);
  schedule();
  return { label, budgetMs, workMs, waitMs, waitAllowanceMs: () => Math.max(0, WAIT_FOR_SLOT_MS - waitMs()), expired, stop };
}

const active: WorkClock[] = [];

export function currentWorkClock(): WorkClock | undefined {
  return active[active.length - 1];
}

export async function underWorkClock<T>(label: string, budgetMs: number, task: () => Promise<T> | T): Promise<T> {
  const clock = startWorkClock(label, budgetMs);
  active.push(clock);
  try {
    return await Promise.race([Promise.resolve().then(task), clock.expired]);
  } finally {
    clock.stop();
    active.splice(active.indexOf(clock), 1);
  }
}

export function envelopeMs(budgetMs: number): number {
  return budgetMs + WAIT_FOR_SLOT_MS + ENVELOPE_GRACE_MS;
}

declare module "vitest" {
  interface TaskMeta {
    workBudgetMs?: number;
  }
}

export function workBudget(budgetMs: number): { timeout: number; meta: { workBudgetMs: number } } {
  return { timeout: envelopeMs(budgetMs), meta: { workBudgetMs: budgetMs } };
}

export function withWorkBudget<Result>(budgetMs: number, hook: () => Promise<Result> | Result): () => Promise<Result> {
  return () => underWorkClock(`hook of "${testFile()}"`, budgetMs, hook);
}
