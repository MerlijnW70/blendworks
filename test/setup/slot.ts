import { basename } from "node:path";
import { vi } from "vitest";
import { acquireSlot, acquireSlotSync, type Slot } from "../../scripts/lib/slots.js";
import { currentWorkClock, envelopeMs, WAIT_FOR_SLOT_MS } from "./work-clock.js";

export { WAIT_FOR_SLOT_MS };
export const BLENDER_TEST_TIMEOUT_MS = 10 * 60_000;

let declared = false;

export function useBlenderSlot(): void {
  declared = true;
  vi.setConfig({ testTimeout: envelopeMs(BLENDER_TEST_TIMEOUT_MS), hookTimeout: envelopeMs(BLENDER_TEST_TIMEOUT_MS) });
}

export function blenderSlotHeld(): boolean {
  return declared;
}

export function defaultWorkBudgetMs(): number | undefined {
  return declared ? BLENDER_TEST_TIMEOUT_MS : undefined;
}

export function isBlenderCommand(command: string): boolean {
  return /^blender(\.exe)?$/i.test(basename(command));
}

function waitAllowanceMs(): number {
  return currentWorkClock()?.waitAllowanceMs() ?? WAIT_FOR_SLOT_MS;
}

export type Holding = "bounded" | "lasting";

const holding = { bounded: 0, lasting: 0 };

export class NestedSlotError extends Error {
  constructor(reason: string) {
    super(`a test asked for a Blender slot while ${reason}; let that process exit first, or two test files could wait on each other forever`);
  }
}

export function slotsHeld(): { bounded: number; lasting: number } {
  return { ...holding };
}

function claim(kind: Holding, blocking: boolean): void {
  if (holding.lasting > 0) throw new NestedSlotError("a session it started still holds one");
  if (blocking && holding.bounded > 0) throw new NestedSlotError("one of its processes holds one and a blocking wait would stall it");
  holding[kind] += 1;
}

function held(slot: Slot, kind: Holding): Slot {
  let released = false;
  return {
    ...slot,
    release: () => {
      if (!released) {
        released = true;
        holding[kind] -= 1;
      }
      slot.release();
    },
  };
}

export async function takeSlot(kind: Holding = "bounded"): Promise<Slot> {
  claim(kind, false);
  try {
    return held(await acquireSlot({ timeoutMs: waitAllowanceMs() }), kind);
  } catch (error) {
    holding[kind] -= 1;
    throw error;
  }
}

export async function whileProcessRuns<T>(task: () => Promise<T>): Promise<T> {
  const slot = await takeSlot();
  try {
    return await task();
  } finally {
    slot.release();
  }
}

export async function untilProcessExits<T>(start: () => Promise<T>, exited: (started: T) => Promise<unknown>): Promise<T> {
  const slot = await takeSlot("lasting");
  try {
    const started = await start();
    void exited(started).finally(() => slot.release());
    return started;
  } catch (error) {
    slot.release();
    throw error;
  }
}

export function whileProcessRunsSync<T>(task: () => T): T {
  claim("bounded", true);
  let slot: Slot;
  try {
    slot = held(acquireSlotSync({ timeoutMs: waitAllowanceMs() }), "bounded");
  } catch (error) {
    holding.bounded -= 1;
    throw error;
  }
  try {
    return task();
  } finally {
    slot.release();
  }
}
